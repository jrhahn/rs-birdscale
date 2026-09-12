//! Turning readings into InfluxDB line protocol, and getting them into QuestDB
//! in batches.
//!
//! The batch exists for the database's sake, not for the network's: every
//! commit fans out into a refresh of the `_1m` materialized view and a WAL
//! apply, so committing once per reading would multiply that by the number of
//! channels. The fleet produces a few readings a second at the very most, so a
//! five-second window costs nothing anyone can see on a chart.

use std::borrow::Cow;
use std::sync::Arc;
use std::time::Duration;

use tokio::sync::mpsc;
use tracing::{debug, error, info, warn};

use super::client::Client;
use crate::model::{Micros, Reading};
use crate::state::Stats;

/// What the MQTT side hands to the writer.
#[derive(Debug, Clone)]
pub enum Record {
    Reading(Reading),
    Status {
        node: String,
        online: bool,
        at: Micros,
    },
}

/// Beyond this, a database that has been unreachable for a long time is costing
/// more memory than the backlog is worth. At the fleet's rate (~50 readings a
/// minute) this is over a day of buffering.
const MAX_PENDING_LINES: usize = 100_000;

/// Escape the characters ILP gives meaning to inside a measurement or tag.
///
/// Node ids and reading keys are `[a-z0-9_]` today, so this never fires in
/// practice. It is here because the values come off MQTT topics, and a topic is
/// whatever someone publishes to -- an unescaped space would silently split the
/// line into a different measurement and a stray field.
pub fn escape_tag(raw: &str) -> Cow<'_, str> {
    if !raw.contains([',', ' ', '=', '\\', '\n', '\r', '"']) {
        return Cow::Borrowed(raw);
    }
    let mut out = String::with_capacity(raw.len() + 8);
    for c in raw.chars() {
        match c {
            ',' | ' ' | '=' | '\\' | '"' => {
                out.push('\\');
                out.push(c);
            }
            '\n' | '\r' => out.push(' '),
            other => out.push(other),
        }
    }
    Cow::Owned(out)
}

/// One reading as a line of ILP.
///
/// The value is formatted with `{:?}` rather than `{}` so it always carries a
/// decimal point: ILP infers a column type from the literal, and `412` is a
/// LONG while `412.0` is a DOUBLE. Since the table is created explicitly with a
/// DOUBLE column, the integer spelling would be a type error on every whole
/// number -- CO2 in ppm, a visit count, an RSSI in dBm. Most of the fleet's
/// readings, in other words.
pub fn ilp_reading(table: &str, r: &Reading) -> String {
    format!(
        "{table},node={node},sensor={sensor} value={value:?} {nanos}\n",
        table = escape_tag(table),
        node = escape_tag(&r.node),
        sensor = escape_tag(&r.sensor),
        value = r.value,
        nanos = r.at * 1_000,
    )
}

/// One availability transition as a line of ILP.
pub fn ilp_status(table: &str, node: &str, online: bool, at: Micros) -> String {
    format!(
        "{table},node={node} online={online} {nanos}\n",
        table = escape_tag(table),
        node = escape_tag(node),
        online = if online { "t" } else { "f" },
        nanos = at * 1_000,
    )
}

/// Buffers records and flushes them on a timer.
///
/// Runs until the channel closes, then flushes what is left -- a clean shutdown
/// (systemd stopping the unit) should not throw away the current window.
pub async fn run(
    client: Client,
    table: String,
    status_table: String,
    flush_interval: Duration,
    batch_max: usize,
    stats: Arc<Stats>,
    mut rx: mpsc::Receiver<Record>,
) {
    let mut pending = String::new();
    let mut pending_lines = 0usize;
    let mut ticker = tokio::time::interval(flush_interval);
    ticker.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);

    loop {
        tokio::select! {
            maybe = rx.recv() => match maybe {
                Some(record) => {
                    match record {
                        Record::Reading(r) => pending.push_str(&ilp_reading(&table, &r)),
                        Record::Status { node, online, at } =>
                            pending.push_str(&ilp_status(&status_table, &node, online, at)),
                    }
                    pending_lines += 1;
                    // A burst -- the whole fleet reconnecting after a broker
                    // restart -- should not wait out the window in memory.
                    if pending_lines >= batch_max {
                        flush(&client, &mut pending, &mut pending_lines, &stats).await;
                    }
                }
                None => {
                    // Clean shutdown: the current window is data too.
                    if pending_lines > 0 {
                        flush(&client, &mut pending, &mut pending_lines, &stats).await;
                    }
                    info!(unflushed = pending_lines, "ingest channel closed; writer stopping");
                    return;
                }
            },
            _ = ticker.tick() => {
                if pending_lines > 0 {
                    flush(&client, &mut pending, &mut pending_lines, &stats).await;
                }
            }
        }
    }
}

async fn flush(client: &Client, pending: &mut String, lines: &mut usize, stats: &Stats) {
    let body = std::mem::take(pending);
    let count = *lines;
    match client.write_ilp(&body).await {
        Ok(()) => {
            *lines = 0;
            stats.record_write(count as u64);
            debug!(rows = count, "flushed to QuestDB");
        }
        Err(e) => {
            stats.record_write_error();
            if count >= MAX_PENDING_LINES {
                error!(
                    rows = count,
                    error = %e,
                    "QuestDB has been unreachable for {MAX_PENDING_LINES} rows; dropping the backlog"
                );
                stats.record_dropped(count as u64);
                *lines = 0;
            } else {
                warn!(rows = count, error = %e, "flush failed; will retry on the next tick");
                // Put it back in front of whatever arrived while we were
                // waiting, so the table stays in timestamp order where it can.
                let arrived = std::mem::take(pending);
                pending.push_str(&body);
                pending.push_str(&arrived);
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn reading(node: &str, sensor: &str, value: f64) -> Reading {
        Reading {
            node: node.into(),
            sensor: sensor.into(),
            value,
            at: 1_700_000_000_000_000,
        }
    }

    #[test]
    fn a_reading_becomes_one_line_with_nanosecond_time() {
        let line = ilp_reading("readings", &reading("schlafzimmer", "co2", 412.0));
        assert_eq!(
            line,
            "readings,node=schlafzimmer,sensor=co2 value=412.0 1700000000000000000\n"
        );
    }

    #[test]
    fn whole_numbers_keep_their_decimal_point() {
        // Without this the column type inferred from the line is LONG, and the
        // DOUBLE column the schema created rejects it. CO2, RSSI and the visit
        // counter are all whole numbers most of the time.
        for value in [412.0_f64, 0.0, -71.0, 1e9] {
            let line = ilp_reading("readings", &reading("n", "s", value));
            let field = line.split("value=").nth(1).unwrap();
            let literal = field.split(' ').next().unwrap();
            assert!(literal.contains('.') || literal.contains('e'), "{literal}");
        }
    }

    #[test]
    fn fractions_survive_the_round_trip() {
        let line = ilp_reading("readings", &reading("bad", "humidity", 55.9));
        assert!(line.contains("value=55.9 "), "{line}");
    }

    #[test]
    fn status_is_a_boolean_field() {
        let line = ilp_status("node_status", "terrasse", false, 1_700_000_000_000_000);
        assert_eq!(
            line,
            "node_status,node=terrasse online=f 1700000000000000000\n"
        );
        let line = ilp_status("node_status", "terrasse", true, 1_700_000_000_000_000);
        assert!(line.contains("online=t "), "{line}");
    }

    #[test]
    fn tags_that_could_break_a_line_are_escaped() {
        assert_eq!(escape_tag("plain_key"), "plain_key");
        assert_eq!(escape_tag("with space"), "with\\ space");
        assert_eq!(escape_tag("a,b=c"), "a\\,b\\=c");
        assert_eq!(escape_tag("back\\slash"), "back\\\\slash");
        // A newline would end the line early and turn the rest into a second,
        // malformed record -- the one case where escaping is not enough.
        assert_eq!(escape_tag("two\nlines"), "two lines");
    }

    #[test]
    fn an_escaped_topic_still_produces_exactly_one_line() {
        let line = ilp_reading("readings", &reading("odd node", "a=b", 1.5));
        assert_eq!(line.matches('\n').count(), 1);
        assert!(line.ends_with('\n'));
        assert!(
            line.starts_with("readings,node=odd\\ node,sensor=a\\=b "),
            "{line}"
        );
    }
}

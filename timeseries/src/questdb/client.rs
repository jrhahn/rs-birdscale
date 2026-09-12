//! The thin HTTP layer over QuestDB: `/exec` for SQL, `/write` for ILP.
//!
//! Both the ingest path and the read path go over the same port (9000) and the
//! same credentials, which is why they share one client rather than one each.
//! There is no connection pool to tune and no wire protocol to speak -- ILP
//! over HTTP is a POST of newline-separated text, and SQL is a GET with the
//! query in the URL.

use anyhow::{bail, Context, Result};
use serde::Deserialize;

/// One `/exec` response, with just enough structure to read a column out of it
/// by name.
///
/// Addressing columns by name rather than by position is not pedantry: several
/// queries here are assembled from a tier table, so the column order of a
/// rollup read and a raw read are the same by construction *today* and there is
/// no reason to let that be load-bearing.
#[derive(Debug, Deserialize)]
pub struct Dataset {
    #[serde(default)]
    pub columns: Vec<Column>,
    #[serde(default)]
    pub dataset: Vec<Vec<serde_json::Value>>,
    /// Present instead of the rest when QuestDB rejected the query.
    #[serde(default)]
    pub error: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct Column {
    pub name: String,
}

impl Dataset {
    pub fn column_index(&self, name: &str) -> Option<usize> {
        self.columns.iter().position(|c| c.name == name)
    }

    /// A column index, or an error naming what was actually returned. Every
    /// caller needs its columns, so failing loudly beats a row of `None`s that
    /// renders as an empty chart.
    pub fn require(&self, name: &str) -> Result<usize> {
        self.column_index(name).with_context(|| {
            let have: Vec<&str> = self.columns.iter().map(|c| c.name.as_str()).collect();
            format!("column {name:?} missing from the result; got {have:?}")
        })
    }

    pub fn rows(&self) -> &[Vec<serde_json::Value>] {
        &self.dataset
    }
}

/// Reads a JSON value that QuestDB may render as a number or, for the wider
/// integer types, as a string.
pub fn as_f64(v: &serde_json::Value) -> Option<f64> {
    match v {
        serde_json::Value::Number(n) => n.as_f64(),
        serde_json::Value::String(s) => s.parse().ok(),
        _ => None,
    }
}

pub fn as_i64(v: &serde_json::Value) -> Option<i64> {
    match v {
        serde_json::Value::Number(n) => n.as_i64(),
        serde_json::Value::String(s) => s.parse().ok(),
        _ => None,
    }
}

pub fn as_str(v: &serde_json::Value) -> Option<&str> {
    v.as_str()
}

/// Percent-encode a statement for the `query=` parameter.
///
/// Hand-rolled rather than pulled in: SQL is mostly punctuation, and the whole
/// rule is "keep the unreserved set, escape the rest" -- which is also the only
/// thing standing between a `+` in a statement and a space arriving at the
/// database. Space is written `%20` rather than `+` because the two are only
/// interchangeable in form bodies, not in a URL's query string.
pub fn percent_encode(raw: &str) -> String {
    let mut out = String::with_capacity(raw.len() * 2);
    for byte in raw.as_bytes() {
        match byte {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                out.push(*byte as char)
            }
            other => out.push_str(&format!("%{other:02X}")),
        }
    }
    out
}

#[derive(Clone)]
pub struct Client {
    http: reqwest::Client,
    base: String,
    credentials: Option<(String, String)>,
}

impl Client {
    pub fn new(base: &str, user: &str, password: &str) -> Result<Self> {
        let http = reqwest::Client::builder()
            // Long enough for a first-creation view backfill to answer, short
            // enough that a wedged database surfaces as an error rather than a
            // hung task.
            .timeout(std::time::Duration::from_secs(120))
            .build()
            .context("building the QuestDB HTTP client")?;
        let credentials = (!user.is_empty()).then(|| (user.to_string(), password.to_string()));
        Ok(Self {
            http,
            base: base.trim_end_matches('/').to_string(),
            credentials,
        })
    }

    fn authed(&self, rb: reqwest::RequestBuilder) -> reqwest::RequestBuilder {
        match &self.credentials {
            Some((user, password)) => rb.basic_auth(user, Some(password)),
            None => rb,
        }
    }

    /// Run a statement. Works for both queries and DDL -- QuestDB answers DDL
    /// with an empty dataset and the same envelope.
    pub async fn exec(&self, sql: &str) -> Result<Dataset> {
        let url = format!("{}/exec?query={}", self.base, percent_encode(sql));
        let response = self
            .authed(self.http.get(&url))
            .send()
            .await
            .with_context(|| format!("POST {url}"))?;

        let status = response.status();
        let body = response.text().await.context("reading the response body")?;

        // A rejected statement comes back as 400 with a JSON body carrying the
        // message and the offset it failed at. Both are worth keeping: the
        // offset is what tells a generated statement apart from a typo.
        let parsed: Dataset = serde_json::from_str(&body).with_context(|| {
            format!("QuestDB returned {status} and a body that is not a result: {body:.400}")
        })?;
        if let Some(error) = parsed.error {
            bail!("QuestDB rejected `{sql}`: {error}");
        }
        if !status.is_success() {
            bail!("QuestDB returned {status} for `{sql}`: {body:.400}");
        }
        Ok(parsed)
    }

    /// Ingest a block of InfluxDB line protocol.
    ///
    /// `precision=n` is spelled out rather than left to the default so a
    /// QuestDB whose default ever changes cannot silently reinterpret the
    /// timestamps -- a factor of 1000 there would put every reading in 1970 or
    /// in the far future, and either is a mess to unpick afterwards.
    pub async fn write_ilp(&self, body: &str) -> Result<()> {
        if body.is_empty() {
            return Ok(());
        }
        let url = format!("{}/write?precision=n", self.base);
        let response = self
            .authed(self.http.post(&url).body(body.to_owned()))
            .send()
            .await
            .with_context(|| format!("POST {url}"))?;

        let status = response.status();
        if status.is_success() {
            return Ok(());
        }
        let body = response.text().await.unwrap_or_default();
        bail!("QuestDB rejected the ILP batch with {status}: {body:.400}");
    }

    /// Cheapest possible round trip, used to tell "not up yet" from "up and
    /// refusing us" at start-up.
    pub async fn ping(&self) -> Result<()> {
        self.exec("SELECT 1").await.map(|_| ())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn dataset(json: &str) -> Dataset {
        serde_json::from_str(json).unwrap()
    }

    #[test]
    fn columns_are_addressed_by_name() {
        let d = dataset(
            r#"{"columns":[{"name":"ts","type":"LONG"},{"name":"lo","type":"DOUBLE"}],
                "dataset":[[1,2.5]],"count":1}"#,
        );
        assert_eq!(d.require("lo").unwrap(), 1);
        assert!(d.require("nope").is_err());
        assert_eq!(d.rows().len(), 1);
    }

    #[test]
    fn a_missing_column_error_names_what_was_returned() {
        let d = dataset(r#"{"columns":[{"name":"ts","type":"LONG"}],"dataset":[]}"#);
        let err = d.require("av").unwrap_err().to_string();
        assert!(err.contains("\"av\""), "{err}");
        assert!(err.contains("ts"), "{err}");
    }

    #[test]
    fn numbers_are_read_whether_quoted_or_not() {
        // QuestDB renders LONG as a number, but a value near the i64 edges can
        // come back as a string; both spellings have to read the same.
        assert_eq!(as_i64(&serde_json::json!(17)), Some(17));
        assert_eq!(as_i64(&serde_json::json!("17")), Some(17));
        assert_eq!(as_f64(&serde_json::json!(1.5)), Some(1.5));
        assert_eq!(as_f64(&serde_json::json!("1.5")), Some(1.5));
        assert_eq!(as_f64(&serde_json::json!(null)), None);
        assert_eq!(as_str(&serde_json::json!("bad")), Some("bad"));
    }

    #[test]
    fn a_statement_survives_the_query_string() {
        // Everything a generated statement is made of: spaces, quotes,
        // parentheses, commas, slashes -- and a `+`, which is the one that
        // would arrive as a space if this used the form-body encoding.
        assert_eq!(percent_encode("SELECT 1"), "SELECT%201");
        assert_eq!(percent_encode("a+b"), "a%2Bb");
        assert_eq!(percent_encode("x='y'"), "x%3D%27y%27");
        assert_eq!(percent_encode("f(g),h"), "f%28g%29%2Ch");
        // Unreserved characters are left alone, so a statement stays readable
        // in a server log.
        assert_eq!(
            percent_encode("readings_1d.value-2~a"),
            "readings_1d.value-2~a"
        );
    }

    #[test]
    fn non_ascii_is_encoded_as_utf8_bytes() {
        assert_eq!(percent_encode("°C"), "%C2%B0C");
    }

    #[test]
    fn an_error_envelope_parses_as_one() {
        let d = dataset(r#"{"query":"select 1","error":"unexpected token","position":7}"#);
        assert_eq!(d.error.as_deref(), Some("unexpected token"));
    }
}

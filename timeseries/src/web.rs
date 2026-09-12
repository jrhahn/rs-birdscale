//! The dashboard: four JSON endpoints and three static files.
//!
//! There is no build step and no bundler. The page is served from
//! `include_str!` of the files next door, which means the binary is the whole
//! deployment -- copy it to the home server, point it at the broker, done --
//! and that a running service cannot be half-upgraded, with a new binary
//! serving the old page out of a stale asset directory.

use std::sync::Arc;

use axum::extract::{Query, State};
use axum::http::{header, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::routing::get;
use axum::{Json, Router};
use serde::{Deserialize, Serialize};
use tracing::warn;

use crate::config::Settings;
use crate::model::{now_micros, Channel, Micros};
use crate::questdb::{series, Client};
use crate::state::{Shared, StatsSnapshot};

#[derive(Clone)]
pub struct App {
    pub settings: Arc<Settings>,
    pub client: Client,
    pub shared: Shared,
}

pub fn router(app: App) -> Router {
    Router::new()
        .route("/", get(index))
        .route("/app.js", get(script))
        .route("/style.css", get(stylesheet))
        .route("/api/channels", get(channels))
        .route("/api/series", get(series_handler))
        .route("/api/health", get(health))
        .with_state(app)
}

/// Anything that goes wrong below becomes a 500 with the reason in it.
///
/// The reason is shown in the dashboard's footer rather than swallowed: on a
/// home server the person reading the chart is the person who can fix the
/// database, and "QuestDB rejected ... : table does not exist" is the whole
/// diagnosis.
struct ApiError(anyhow::Error);

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        warn!(error = %self.0, "request failed");
        (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(serde_json::json!({ "error": self.0.to_string() })),
        )
            .into_response()
    }
}

impl<E: Into<anyhow::Error>> From<E> for ApiError {
    fn from(e: E) -> Self {
        ApiError(e.into())
    }
}

type ApiResult<T> = std::result::Result<T, ApiError>;

async fn index() -> impl IntoResponse {
    (
        [(header::CONTENT_TYPE, "text/html; charset=utf-8")],
        include_str!("../assets/index.html"),
    )
}

async fn script() -> impl IntoResponse {
    (
        [(header::CONTENT_TYPE, "text/javascript; charset=utf-8")],
        include_str!("../assets/app.js"),
    )
}

async fn stylesheet() -> impl IntoResponse {
    (
        [(header::CONTENT_TYPE, "text/css; charset=utf-8")],
        include_str!("../assets/style.css"),
    )
}

/// Every channel, with its labels and its current value.
///
/// The list is the union of three sources, because each knows something the
/// others do not: QuestDB knows every channel that ever stored a row (including
/// nodes that are switched off today), the retained discovery messages know the
/// names and units, and the bridge's memory knows what arrived in the last few
/// seconds -- a brand-new sensor appears here before its first row is flushed.
async fn channels(State(app): State<App>) -> ApiResult<Json<Vec<Channel>>> {
    let base = &app.settings.questdb.table;
    let views = app.shared.views();

    let mut keys: Vec<(String, String)> = series::fetch_channels(&app.client, base, &views)
        .await?
        .into_iter()
        .map(|(node, sensor, _)| (node, sensor))
        .collect();
    for known in app.shared.known_channels() {
        if !keys.contains(&known) {
            keys.push(known);
        }
    }

    // One `LATEST ON` for the whole fleet rather than a query per channel.
    let latest = series::fetch_latest(&app.client, base)
        .await
        .unwrap_or_default();
    let status = series::fetch_status(&app.client, &app.settings.questdb.status_table)
        .await
        .unwrap_or_default();

    let mut out: Vec<Channel> = keys
        .into_iter()
        .map(|(node, sensor)| {
            // Memory wins over the database: it is at most a flush interval
            // fresher, and never staler.
            let live = app.shared.live(&node, &sensor);
            let stored = latest
                .iter()
                .find(|(n, s, _, _)| *n == node && *s == sensor)
                .map(|(_, _, v, t)| (*v, *t));
            let (last_value, last_at_ms) = match (live, stored) {
                (Some(l), Some(s)) if s.1 > l.1 => (Some(s.0), Some(s.1)),
                (Some(l), _) => (Some(l.0), Some(l.1)),
                (None, Some(s)) => (Some(s.0), Some(s.1)),
                (None, None) => (None, None),
            };
            Channel {
                meta: app.shared.meta(&node, &sensor).unwrap_or_default(),
                online: app
                    .shared
                    .online(&node)
                    .or_else(|| status.iter().find(|(n, _)| *n == node).map(|(_, o)| *o)),
                node,
                sensor,
                last_value,
                last_at_ms,
            }
        })
        .collect();

    // Stable order, so the sidebar does not reshuffle between polls.
    out.sort_by(|a, b| (&a.node, &a.sensor).cmp(&(&b.node, &b.sensor)));
    Ok(Json(out))
}

#[derive(Debug, Deserialize)]
struct SeriesParams {
    node: String,
    sensor: String,
    /// Epoch milliseconds. Defaults to the last 24 hours.
    from: Option<i64>,
    to: Option<i64>,
    /// How many buckets the caller can draw. Bounded so a hand-written URL
    /// cannot ask for a million rows.
    points: Option<i64>,
}

async fn series_handler(
    State(app): State<App>,
    Query(params): Query<SeriesParams>,
) -> ApiResult<Json<series::Series>> {
    let now = now_micros();
    let to: Micros = params.to.map(|ms| ms * 1_000).unwrap_or(now);
    let from: Micros = params
        .from
        .map(|ms| ms * 1_000)
        .unwrap_or(to - 24 * 60 * 60 * 1_000_000);
    if from >= to {
        return Err(ApiError(anyhow::anyhow!(
            "from ({from}) must be before to ({to})"
        )));
    }
    let points = params.points.unwrap_or(600).clamp(2, 5_000);

    let series = series::fetch_series(
        &app.client,
        &app.settings.questdb.table,
        &app.shared.views(),
        &series::Request {
            node: &params.node,
            sensor: &params.sensor,
            from,
            to,
            points,
        },
    )
    .await?;
    Ok(Json(series))
}

#[derive(Serialize)]
struct Health {
    broker_connected: bool,
    database_reachable: bool,
    table: String,
    retention: Option<String>,
    views: Vec<String>,
    #[serde(flatten)]
    stats: StatsSnapshot,
}

async fn health(State(app): State<App>) -> Json<Health> {
    let database_reachable = app.client.ping().await.is_ok();
    Json(Health {
        broker_connected: app.shared.broker_connected(),
        database_reachable,
        table: app.settings.questdb.table.clone(),
        retention: app.settings.retention().as_sql().map(|s| s.to_string()),
        views: app.shared.views(),
        stats: app.shared.stats().snapshot(),
    })
}

#[cfg(test)]
mod tests {
    //! The handlers all need a live QuestDB, so what is tested here is the
    //! part that does not: that the assets the binary embeds are the ones the
    //! page actually asks for. A renamed file would otherwise fail at run time
    //! as a blank dashboard.

    #[test]
    fn the_page_references_exactly_the_assets_that_are_served() {
        let html = include_str!("../assets/index.html");
        assert!(html.contains("/style.css"), "stylesheet link missing");
        assert!(html.contains("/app.js"), "script tag missing");
    }

    #[test]
    fn the_script_calls_the_endpoints_the_router_declares() {
        let js = include_str!("../assets/app.js");
        for route in ["/api/channels", "/api/series", "/api/health"] {
            assert!(js.contains(route), "{route} is never called");
        }
    }

    #[test]
    fn the_page_pulls_nothing_from_the_internet() {
        // The home server's dashboard has to work when the line is down, and
        // a chart library from a CDN is also a third party watching the house.
        let html = include_str!("../assets/index.html");
        assert!(!html.contains("http://"), "{html}");
        assert!(!html.contains("https://"), "{html}");
    }
}

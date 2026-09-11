//! Discovery metadata for the HX711 load cell.
//!
//! The load cell is not a plain [`Sensor`](super::Sensor): its reading feeds the
//! tare baseline and the bird-presence edge detection in `main`, and the raw ->
//! grams conversion needs the runtime calibration from [`crate::config`]. So the
//! HX711 keeps its own path and only contributes its Home Assistant descriptor
//! here, so the discovery publisher (#16) can treat it like any other reading.

use core::fmt::Write as _;

use heapless::String;

use super::EntityDescriptor;

pub const DESCRIPTORS: &[EntityDescriptor] = &[
    EntityDescriptor {
        key: "weight",
        name: "Gewicht",
        unit: "g",
        device_class: "weight",
        state_class: "measurement",
    },
    // How long the load stayed on the cell. Only a visit produces one, so this
    // entity is stale between birds by design — it is the length of the *last*
    // visit, not a live value. `main` watches a visit through while awake
    // (see `crate::presence`), which is what makes the number better than the
    // deep-sleep interval it used to be quantised to.
    // The count, kept in RTC RAM and incremented at the arrival rather than at
    // the publish -- see `crate::state::count_visit` for why deriving it in
    // Home Assistant would undercount. `total_increasing` is what makes Home
    // Assistant keep it forever: statistics store a sum for that state class
    // and never purge it, while a `measurement` keeps only hourly mean/min/max
    // and the individual visits are gone with the 10-day raw history.
    //
    // Named for the birds rather than for the mechanism: the panel's Zuhause
    // screen picks up any entity with `Vogel` in its name and reads `heute` or
    // `gesamt` from the rest (see `trmnl/README.md` in home-server).
    EntityDescriptor {
        key: "visits",
        name: "Vögel gesamt",
        unit: "",
        device_class: "",
        state_class: "total_increasing",
    },
    EntityDescriptor {
        key: "visit",
        name: "Besuchsdauer",
        unit: "s",
        device_class: "duration",
        state_class: "measurement",
    },
];

/// Format the visit counter for MQTT.
///
/// A bare integer. Home Assistant needs no unit to treat a `total_increasing`
/// number as a count, and giving it one ("Besuche") would put that word on
/// every axis and tooltip for nothing.
pub fn write_visits(buf: &mut String<16>, count: u32) {
    let _ = write!(buf, "{}", count);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_counter_is_total_increasing_so_statistics_keep_it() {
        let d = DESCRIPTORS
            .iter()
            .find(|d| d.key == "visits")
            .expect("the visit counter is announced");
        assert_eq!(d.state_class, "total_increasing");
        assert!(d.name.contains("Vögel"), "the panel matches on the name");
    }

    #[test]
    fn a_count_formats_as_a_bare_integer() {
        for (n, expected) in [(0u32, "0"), (1, "1"), (75, "75"), (u32::MAX, "4294967295")] {
            let mut buf = String::new();
            write_visits(&mut buf, n);
            assert_eq!(buf.as_str(), expected);
        }
    }
}

# Health Pulse

A small full-stack prototype built on [Junction's](https://docs.junction.com) health-data
API. It answers one question:

> **What has changed in this patient's recent health data?**

Rather than rendering every available wearable metric, Health Pulse compares a recent
7-day window against the preceding 21-day baseline and surfaces only the changes that
cross a threshold — with an evidence view showing exactly how each number was derived.

> [!IMPORTANT]
> This prototype is for demonstration purposes and is not a medical diagnostic tool.

Setup, architecture and design rationale are documented below as the project takes shape.

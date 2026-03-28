from __future__ import annotations

import os
import random
import threading
import time
from collections import deque
from dataclasses import dataclass
from statistics import fmean, median

import requests
from flask import Flask, jsonify, redirect, render_template_string, request, url_for

try:
    from gpiozero import Buzzer, LED
except ImportError:  # Local development fallback when gpiozero is unavailable.
    Buzzer = None  # type: ignore[assignment]
    LED = None  # type: ignore[assignment]

try:
    import board
    import adafruit_dht
except ImportError:  # Local development fallback when adafruit libs are unavailable.
    board = None  # type: ignore[assignment]
    adafruit_dht = None  # type: ignore[assignment]

try:
    import busio
    import adafruit_ads1x15.ads1115 as ADS
    from adafruit_ads1x15.analog_in import AnalogIn
except ImportError:  # Local development fallback when adafruit libs are unavailable.
    busio = None  # type: ignore[assignment]
    ADS = None  # type: ignore[assignment]
    AnalogIn = None  # type: ignore[assignment]


HTML = """
<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Atmosfera 2077 - Panel Powietrza</title>
    <style>
        :root {
            --sky: #7dc6f9;
            --rain: #2f8bbd;
            --jungle: #1f8a62;
            --smog: #a88c67;
            --ink: #dbe8f7;
            --ink-muted: #94abc5;
            --card: rgba(10, 19, 34, 0.72);
            --card-stroke: rgba(130, 175, 225, 0.22);
            --ok: #33d17a;
            --warn: #f4b63d;
            --alert: #f15a5a;
        }

        * { box-sizing: border-box; }

        body {
            margin: 0;
            min-height: 100vh;
            font-family: "Bahnschrift", "Trebuchet MS", sans-serif;
            color: var(--ink);
            --icon-accent: #c7d9ef;
            --icon-bg: rgba(214, 233, 251, 0.12);
            background:
                radial-gradient(1200px 700px at 15% 20%, rgba(125, 198, 249, 0.35), transparent 60%),
                radial-gradient(900px 500px at 80% 10%, rgba(31, 138, 98, 0.22), transparent 65%),
                linear-gradient(140deg, #080f1c, #0b1a2c 40%, #101f2f);
            padding: 22px;
            transition: background 600ms ease;
            overflow-x: hidden;
        }

        body::before,
        body::after {
            content: "";
            position: fixed;
            pointer-events: none;
            inset: 0;
            z-index: -1;
        }

        body::before {
            background:
                linear-gradient(90deg, rgba(255, 255, 255, 0.06) 1px, transparent 1px),
                linear-gradient(rgba(255, 255, 255, 0.04) 1px, transparent 1px);
            background-size: 46px 46px;
            background-position: 0 0, 0 0;
            mask-image: radial-gradient(circle at center, #000 35%, transparent 100%);
        }

        body::after {
            background: radial-gradient(circle at 50% 120%, rgba(47, 139, 189, 0.33), transparent 55%);
            transform: none;
            transition: background 450ms ease;
        }

        body[data-rain="on"]::after {
            background:
                repeating-linear-gradient(
                    100deg,
                    rgba(130, 193, 232, 0.08) 0px,
                    rgba(130, 193, 232, 0.08) 2px,
                    transparent 2px,
                    transparent 14px
                ),
                radial-gradient(circle at 50% 120%, rgba(47, 139, 189, 0.5), transparent 55%);
        }

        body[data-aq="good"] {
            --icon-accent: #66efad;
            --icon-bg: rgba(51, 209, 122, 0.22);
            background:
                radial-gradient(1200px 700px at 15% 20%, rgba(125, 198, 249, 0.35), transparent 60%),
                radial-gradient(900px 500px at 80% 10%, rgba(31, 138, 98, 0.22), transparent 65%),
                linear-gradient(140deg, #080f1c, #0b1a2c 40%, #101f2f);
        }

        body[data-aq="fair"] {
            --icon-accent: #ffd26a;
            --icon-bg: rgba(244, 182, 61, 0.2);
            background:
                radial-gradient(1200px 700px at 15% 20%, rgba(244, 182, 61, 0.23), transparent 60%),
                radial-gradient(900px 500px at 80% 10%, rgba(47, 139, 189, 0.2), transparent 65%),
                linear-gradient(140deg, #0f121b, #272413 48%, #1e2430);
        }

        body[data-aq="poor"] {
            --icon-accent: #ffa4a4;
            --icon-bg: rgba(241, 90, 90, 0.2);
            background:
                radial-gradient(1200px 700px at 15% 20%, rgba(241, 90, 90, 0.28), transparent 60%),
                radial-gradient(900px 500px at 80% 10%, rgba(168, 140, 103, 0.27), transparent 65%),
                linear-gradient(140deg, #120f13, #26171a 45%, #2d2420);
        }

        .shell {
            width: min(1180px, 100%);
            margin: 0 auto;
            display: grid;
            gap: 16px;
        }

        .hero {
            border: 1px solid var(--card-stroke);
            border-radius: 22px;
            padding: 20px;
            background: linear-gradient(160deg, rgba(13, 27, 49, 0.85), rgba(6, 13, 23, 0.72));
            box-shadow: 0 30px 80px rgba(1, 5, 12, 0.45), inset 0 1px 0 rgba(204, 232, 255, 0.2);
            animation: rise 700ms ease both;
        }

        .hero.alarm-kick {
            animation: rise 700ms ease both, alarmKick 320ms ease;
        }

        .headline {
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            align-items: center;
            justify-content: space-between;
        }

        h1 {
            margin: 0;
            font-size: clamp(1.4rem, 3.2vw, 2.4rem);
            letter-spacing: 0.03em;
            text-transform: uppercase;
        }

        .subtitle {
            margin-top: 8px;
            color: var(--ink-muted);
            font-size: 0.95rem;
            line-height: 1.45;
        }

        .quality-pill {
            border: 1px solid rgba(148, 171, 197, 0.38);
            border-radius: 999px;
            padding: 7px 12px;
            font-size: 0.85rem;
            background: rgba(148, 171, 197, 0.08);
            color: var(--ink);
        }

        .dynamic-stage {
            margin-top: 16px;
            border-radius: 16px;
            border: 1px solid rgba(255, 255, 255, 0.16);
            padding: 12px;
            background: linear-gradient(145deg, rgba(20, 36, 58, 0.66), rgba(10, 22, 38, 0.6));
        }

        .signal-row {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
            gap: 10px;
        }

        .chip {
            min-height: 70px;
            border-radius: 12px;
            border: 1px solid rgba(181, 213, 241, 0.22);
            background: rgba(11, 23, 39, 0.58);
            padding: 10px;
            position: relative;
            overflow: hidden;
            isolation: isolate;
        }

        .chip::after {
            content: "";
            position: absolute;
            inset: -40% auto -40% -55%;
            width: 45%;
            transform: skewX(-20deg) translateX(-150%);
            background: linear-gradient(
                90deg,
                transparent,
                rgba(255, 255, 255, 0.25),
                transparent
            );
            opacity: 0;
            pointer-events: none;
        }

        .chip.active-shine::after {
            opacity: 0;
            animation: none;
        }

        .chip-label {
            display: block;
            color: var(--ink-muted);
            font-size: 0.76rem;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }

        .chip-main {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-top: 6px;
            font-weight: 700;
        }

        .icon {
            width: 30px;
            height: 30px;
            border-radius: 10px;
            display: grid;
            place-items: center;
            font-size: 1rem;
            color: var(--icon-accent);
            background: var(--icon-bg);
            transition: opacity 170ms ease, transform 170ms ease, color 350ms ease, background 350ms ease;
        }

        .icon svg {
            width: 18px;
            height: 18px;
            fill: currentColor;
            display: block;
        }

        .icon.is-swapping {
            opacity: 0.2;
            transform: scale(0.88);
        }

        .icon.icon-pop {
            animation: iconPop 220ms ease;
        }

        .chip.green {
            border-color: rgba(82, 214, 132, 0.42);
            background: linear-gradient(140deg, rgba(20, 70, 44, 0.55), rgba(14, 37, 28, 0.72));
        }

        .chip.alert {
            border-color: rgba(241, 90, 90, 0.5);
            background: linear-gradient(140deg, rgba(112, 41, 41, 0.52), rgba(42, 21, 21, 0.74));
        }

        .pulse {
            animation: none;
        }

        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 12px;
        }

        .status {
            border: 1px solid var(--card-stroke);
            border-radius: 16px;
            padding: 14px;
            background: var(--card);
            box-shadow: inset 0 1px 0 rgba(210, 231, 255, 0.12);
            animation: rise 620ms ease both;
        }

        .status h3,
        .status strong {
            margin: 0;
            font-size: 0.98rem;
            letter-spacing: 0.05em;
            text-transform: uppercase;
            color: #d2e4fa;
        }

        .dot {
            width: 13px;
            height: 13px;
            border-radius: 999px;
            display: inline-block;
            margin-right: 8px;
            box-shadow: 0 0 16px currentColor;
            vertical-align: middle;
        }

        .value {
            margin-top: 8px;
            font-size: clamp(1.2rem, 2.6vw, 1.9rem);
            font-weight: 700;
            letter-spacing: 0.03em;
        }

        .subtle {
            display: block;
            margin-top: 6px;
            color: var(--ink-muted);
            font-size: 0.9rem;
            line-height: 1.35;
        }

        .status-pill {
            display: inline-flex;
            align-items: center;
            gap: 7px;
            margin-top: 8px;
            padding: 6px 10px;
            border-radius: 999px;
            border: 1px solid rgba(148, 171, 197, 0.36);
            background: rgba(148, 171, 197, 0.08);
            font-size: 0.84rem;
            color: var(--ink);
        }

        .status-pill-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: #6b7280;
            box-shadow: 0 0 10px rgba(107, 114, 128, 0.7);
        }

        .status-pill.ok .status-pill-dot {
            background: #33d17a;
            box-shadow: 0 0 12px rgba(51, 209, 122, 0.75);
        }

        .status-pill.error .status-pill-dot {
            background: #f15a5a;
            box-shadow: 0 0 12px rgba(241, 90, 90, 0.75);
        }

        .error { color: #ff8b8b; }

        .air {
            grid-column: 1 / -1;
        }

        .meter {
            margin-top: 12px;
            width: 100%;
            height: 32px;
            border-radius: 10px;
            overflow: hidden;
            border: 1px solid rgba(148, 171, 197, 0.36);
            background: linear-gradient(90deg, rgba(40, 98, 63, 0.35), rgba(153, 115, 44, 0.35), rgba(130, 53, 53, 0.35));
        }

        #air-quality-bar {
            height: 100%;
            width: 0%;
            transition: width 1s ease, background 500ms ease;
            background: var(--ok);
            box-shadow: inset 0 0 20px rgba(255, 255, 255, 0.25);
        }

        .hint {
            margin-top: 14px;
            color: var(--ink-muted);
            font-size: 0.92rem;
            line-height: 1.45;
        }

        @keyframes rise {
            from { opacity: 0; transform: translateY(14px); }
            to { opacity: 1; transform: translateY(0); }
        }

        @keyframes iconPop {
            from { transform: scale(0.9); }
            to { transform: scale(1); }
        }

        @keyframes alarmKick {
            0% { transform: translateX(0); }
            20% { transform: translateX(-4px); }
            40% { transform: translateX(4px); }
            60% { transform: translateX(-3px); }
            80% { transform: translateX(3px); }
            100% { transform: translateX(0); }
        }

        @media (max-width: 820px) {
            body { padding: 14px; }
            .hero { padding: 14px; border-radius: 16px; }
        }

        @media (prefers-reduced-motion: reduce) {
            * {
                animation-duration: 0.01ms !important;
                animation-iteration-count: 1 !important;
                transition-duration: 0.01ms !important;
            }
        }
    </style>
</head>
<body data-aq="unknown">
    <main class="shell">
        <section class="hero">
            <div class="headline">
                <h1>Atmosfera 2077</h1>
                <span id="quality-narrative" class="quality-pill">Skan klimatu: oczekiwanie na dane</span>
            </div>
            <p class="subtitle">Dynamika panelu zalezy od danych: dobre powietrze rozjasnia tlo sloncem, wysoka wilgotnosc uruchamia efekt deszczu, zielona dioda podswietla status, buzzer miga przy alarmie, a wysokie ppm pokazuje ikonke skazenia.</p>
            <div class="dynamic-stage">
                <div class="signal-row">
                    <article class="chip" id="weather-chip">
                        <span class="chip-label">Tlo i pogoda</span>
                        <span class="chip-main"><span class="icon" id="weather-icon"></span><span id="weather-text">Tryb sloneczny</span></span>
                    </article>
                    <article class="chip" id="led-chip">
                        <span class="chip-label">Status diody</span>
                        <span class="chip-main"><span class="icon" id="led-icon"></span><span id="led-chip-text">Brak zielonego trybu</span></span>
                    </article>
                    <article class="chip" id="buzzer-chip">
                        <span class="chip-label">Alarm buzzer</span>
                        <span class="chip-main"><span class="icon" id="buzzer-icon"></span><span id="buzzer-chip-text">Buzzer wylaczony</span></span>
                    </article>
                    <article class="chip" id="pollution-chip">
                        <span class="chip-label">Skazenie / PPM</span>
                        <span class="chip-main"><span class="icon" id="pollution-icon"></span><span id="pollution-text">Poziom ppm stabilny</span></span>
                    </article>
                </div>
            </div>
        </section>

        <section class="grid">
            <div class="status">
                <span class="dot" id="led-dot" style="background: {{ status_color }};"></span>
                <strong>LED Status</strong>
                <div class="value" id="led-mode">{{ current_mode|upper }}</div>
                <span class="subtle" id="led-state-text">RED: {{ "ON" if red_on else "OFF" }} | GREEN: {{ "ON" if green_on else "OFF" }}</span>
            </div>

            <div class="status">
                <strong>Klimat DHT</strong>
                {% if temperature_available %}
                <div class="value" id="temperature-c">{{ "%.2f"|format(temperature_c) }} C</div>
                <span class="subtle" id="humidity-pct">Wilgotnosc: {{ "%.2f"|format(humidity_pct) }} %</span>
                <span class="subtle" id="temperature-f">{{ "%.2f"|format(temperature_f) }} F</span>
                {% else %}
                <div class="value" id="temperature-c">Brak danych</div>
                <span class="subtle" id="humidity-pct">Wilgotnosc: -- %</span>
                <span class="subtle error" id="temperature-f">{{ temperature_error }}</span>
                {% endif %}
            </div>

            <div class="status">
                <strong>Buzzer GPIO16</strong>
                <div class="value" id="buzzer-state">{{ "AKTYWNY" if buzzer_on else "WYLACZONY" }}</div>
                <span class="subtle" id="buzzer-threshold">Aktywuje sie od score >= 67</span>
                <label class="subtle" style="display: flex; align-items: center; gap: 8px; margin-top: 10px;">
                    <input type="checkbox" id="buzzer-manual-toggle" />
                    Reczny buzzer (override)
                </label>
                <span class="subtle" id="buzzer-manual-state">Tryb reczny: wylaczony</span>
            </div>

            <div class="status">
                <strong>MQ135 / ADS1115</strong>
                <div class="value" id="mq135-ppm">-- ppm</div>
                <span class="subtle" id="mq135-voltage">Napiecie: -- V</span>
                <span class="subtle" id="mq135-raw">RAW: --</span>
                <span class="subtle error" id="mq135-error" style="display: none;"></span>
            </div>

            <div class="status">
                <strong>Wysylanie do chmury</strong>
                <label class="subtle" style="display: flex; align-items: center; gap: 8px; margin-top: 10px;">
                    <input type="checkbox" id="cloud-sync-toggle" />
                    ThingSpeak upload
                </label>
                <span class="subtle" id="cloud-sync-state">Status: --</span>
                <span class="status-pill" id="cloud-upload-pill">
                    <span class="status-pill-dot" id="cloud-upload-dot"></span>
                    <span id="cloud-upload-text">Oczekiwanie na wysylke</span>
                </span>
                <span class="subtle" id="cloud-upload-detail"></span>
            </div>

            <div class="status air">
                <strong>Wskaznik Jakosci Powietrza (0-100)</strong>
                <div class="value" id="air-quality-score">-- / 100</div>
                <div class="meter">
                    <div id="air-quality-bar"></div>
                </div>
                <span class="subtle" id="air-quality-level" style="margin-top: 8px;">Status: --</span>
            </div>
        </section>

        <p class="hint">Panel odswieza sie co 2 sekundy. LED oraz buzzer sa sterowane automatycznie przez algorytm jakosci powietrza.</p>
    </main>
    <script>
        const ledDotEl = document.getElementById("led-dot");
        const ledModeEl = document.getElementById("led-mode");
        const ledStateTextEl = document.getElementById("led-state-text");
        const temperatureCEl = document.getElementById("temperature-c");
        const humidityPctEl = document.getElementById("humidity-pct");
        const temperatureFEl = document.getElementById("temperature-f");
        const buzzerStateEl = document.getElementById("buzzer-state");
        const buzzerThresholdEl = document.getElementById("buzzer-threshold");
        const buzzerManualToggleEl = document.getElementById("buzzer-manual-toggle");
        const buzzerManualStateEl = document.getElementById("buzzer-manual-state");
        const mq135PpmEl = document.getElementById("mq135-ppm");
        const mq135VoltageEl = document.getElementById("mq135-voltage");
        const mq135RawEl = document.getElementById("mq135-raw");
        const mq135ErrorEl = document.getElementById("mq135-error");
        const airQualityScoreEl = document.getElementById("air-quality-score");
        const airQualityBarEl = document.getElementById("air-quality-bar");
        const airQualityLevelEl = document.getElementById("air-quality-level");
        const cloudSyncToggleEl = document.getElementById("cloud-sync-toggle");
        const cloudSyncStateEl = document.getElementById("cloud-sync-state");
        const cloudUploadPillEl = document.getElementById("cloud-upload-pill");
        const cloudUploadTextEl = document.getElementById("cloud-upload-text");
        const cloudUploadDetailEl = document.getElementById("cloud-upload-detail");
        const qualityNarrativeEl = document.getElementById("quality-narrative");
        const heroEl = document.querySelector(".hero");
        const weatherChipEl = document.getElementById("weather-chip");
        const weatherIconEl = document.getElementById("weather-icon");
        const weatherTextEl = document.getElementById("weather-text");
        const ledChipEl = document.getElementById("led-chip");
        const ledIconEl = document.getElementById("led-icon");
        const ledChipTextEl = document.getElementById("led-chip-text");
        const buzzerChipEl = document.getElementById("buzzer-chip");
        const buzzerIconEl = document.getElementById("buzzer-icon");
        const buzzerChipTextEl = document.getElementById("buzzer-chip-text");
        const pollutionChipEl = document.getElementById("pollution-chip");
        const pollutionIconEl = document.getElementById("pollution-icon");
        const pollutionTextEl = document.getElementById("pollution-text");
        const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        const isDesktopPointer = window.matchMedia("(pointer: fine)").matches;
        const desktopBeepEnabled = isDesktopPointer;
        let displayedPpm = null;
        let displayedScore = null;
        let lastAqLevel = "unknown";
        let audioCtx = null;
        let audioUnlocked = false;

        const ICONS = {
            sun: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4.5a1 1 0 0 1 1 1V7a1 1 0 1 1-2 0V5.5a1 1 0 0 1 1-1ZM5.64 6.05a1 1 0 0 1 1.41 0l1.06 1.06A1 1 0 1 1 6.7 8.52L5.64 7.46a1 1 0 0 1 0-1.41ZM18.36 6.05a1 1 0 0 1 0 1.41L17.3 8.52a1 1 0 0 1-1.41-1.41l1.06-1.06a1 1 0 0 1 1.41 0ZM12 9a3.5 3.5 0 1 1 0 7 3.5 3.5 0 0 1 0-7Zm-7.5 2a1 1 0 1 1 0 2H3a1 1 0 1 1 0-2h1.5ZM21 11a1 1 0 1 1 0 2h-1.5a1 1 0 1 1 0-2H21ZM6.7 15.48a1 1 0 0 1 1.41 0 1 1 0 0 1 0 1.41l-1.06 1.06a1 1 0 1 1-1.41-1.41l1.06-1.06ZM17.3 15.48l1.06 1.06a1 1 0 0 1-1.41 1.41l-1.06-1.06a1 1 0 0 1 1.41-1.41ZM12 17a1 1 0 0 1 1 1v1.5a1 1 0 1 1-2 0V18a1 1 0 0 1 1-1Z"/></svg>',
            rain: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7.5 16a4.5 4.5 0 1 1 .7-8.95A5.5 5.5 0 0 1 18 9.5 3.5 3.5 0 1 1 18.5 16H7.5Zm-1.2 1.8a1 1 0 0 1 1.4 0l.2.2a1 1 0 0 1-1.4 1.4l-.2-.2a1 1 0 0 1 0-1.4Zm4 0a1 1 0 0 1 1.4 0l.2.2a1 1 0 1 1-1.4 1.4l-.2-.2a1 1 0 0 1 0-1.4Zm4 0a1 1 0 0 1 1.4 0l.2.2a1 1 0 0 1-1.4 1.4l-.2-.2a1 1 0 0 1 0-1.4Z"/></svg>',
            ledOn: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2a5 5 0 0 1 5 5c0 2.3-1.56 4.1-3 5v2h1a1 1 0 1 1 0 2H9a1 1 0 1 1 0-2h1v-2c-1.44-.9-3-2.7-3-5a5 5 0 0 1 5-5Zm-2 16h4l.8 3a1 1 0 0 1-.97 1.24H10.2A1 1 0 0 1 9.23 21L10 18Z"/></svg>',
            ledOff: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2a5 5 0 0 1 5 5c0 2.3-1.56 4.1-3 5v2h1a1 1 0 1 1 0 2H9a1 1 0 1 1 0-2h1v-2c-1.44-.9-3-2.7-3-5a5 5 0 0 1 5-5Zm-2 16h4l.8 3a1 1 0 0 1-.97 1.24H10.2A1 1 0 0 1 9.23 21L10 18Z" opacity=".45"/></svg>',
            buzzerOn: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 10h4l5-4v12l-5-4H4v-4Zm12.5-3.5a1 1 0 0 1 1.4 0A7 7 0 0 1 20 12a7 7 0 0 1-2.1 5.5 1 1 0 1 1-1.4-1.4A5 5 0 0 0 18 12a5 5 0 0 0-1.5-3.6 1 1 0 0 1 0-1.4Zm2.8-2.8a1 1 0 0 1 1.4 0A11 11 0 0 1 24 12a11 11 0 0 1-3.3 8.3 1 1 0 1 1-1.4-1.4A9 9 0 0 0 22 12a9 9 0 0 0-2.7-6.3 1 1 0 0 1 0-1.4Z"/></svg>',
            buzzerOff: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 10h4l5-4v12l-5-4H4v-4Zm11.7-4.3a1 1 0 0 1 1.4 1.4L14.2 10l2.9 2.9a1 1 0 1 1-1.4 1.4L12.8 11.4l-2.9 2.9a1 1 0 1 1-1.4-1.4l2.9-2.9-2.9-2.9a1 1 0 0 1 1.4-1.4l2.9 2.9 2.9-2.9Z" opacity=".7"/></svg>',
            pollution: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M13 3 4 19h18L13 3Zm0 5.5a1 1 0 0 1 1 1V13a1 1 0 1 1-2 0V9.5a1 1 0 0 1 1-1Zm0 8a1.25 1.25 0 1 1 0 2.5 1.25 1.25 0 0 1 0-2.5Z"/></svg>',
            ok: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9.2 16.4 5.8 13a1 1 0 1 1 1.4-1.4l2 2 7.6-7.6a1 1 0 0 1 1.4 1.4l-9 9Z"/></svg>',
            error: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm1 5v6a1 1 0 1 1-2 0V7a1 1 0 1 1 2 0Zm-1 11a1.25 1.25 0 1 1 0-2.5A1.25 1.25 0 0 1 12 18Z"/></svg>'
        };

        function setIcon(iconEl, svgMarkup) {
            if (!iconEl) {
                return;
            }
            if (iconEl.dataset.currentIcon === svgMarkup) {
                return;
            }
            iconEl.innerHTML = svgMarkup;
            iconEl.dataset.currentIcon = svgMarkup;
        }

        function animateNumber(targetEl, fromValue, toValue, options) {
            const { decimals = 0, suffix = "" } = options;
            const safeTarget = Number(toValue);
            if (!Number.isFinite(safeTarget)) {
                targetEl.textContent = `--${suffix}`;
                return null;
            }

            targetEl.textContent = `${safeTarget.toFixed(decimals)}${suffix}`;
            return safeTarget;
        }

        function triggerAlarmKick() {
            if (prefersReducedMotion || !heroEl) {
                return;
            }
            heroEl.classList.remove("alarm-kick");
            void heroEl.offsetWidth;
            heroEl.classList.add("alarm-kick");
            setTimeout(() => {
                heroEl.classList.remove("alarm-kick");
            }, 360);
        }

        function ensureAudioContext() {
            if (!desktopBeepEnabled || typeof window.AudioContext === "undefined") {
                return null;
            }
            if (!audioCtx) {
                audioCtx = new window.AudioContext();
            }
            return audioCtx;
        }

        function unlockAudio() {
            const ctx = ensureAudioContext();
            if (!ctx) {
                return;
            }
            if (ctx.state === "suspended") {
                ctx.resume().then(() => {
                    audioUnlocked = true;
                }).catch(() => {
                    // Ignore unlock failures (browser policy / no gesture yet).
                });
                return;
            }
            audioUnlocked = true;
        }

        function playAlarmBeep() {
            const ctx = ensureAudioContext();
            if (!ctx) {
                return;
            }
            if (!audioUnlocked && ctx.state === "suspended") {
                return;
            }

            const now = ctx.currentTime;
            const oscillator = ctx.createOscillator();
            const gain = ctx.createGain();

            oscillator.type = "square";
            oscillator.frequency.setValueAtTime(920, now);
            oscillator.frequency.exponentialRampToValueAtTime(760, now + 0.12);

            gain.gain.setValueAtTime(0.0001, now);
            gain.gain.exponentialRampToValueAtTime(0.05, now + 0.01);
            gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.14);

            oscillator.connect(gain);
            gain.connect(ctx.destination);
            oscillator.start(now);
            oscillator.stop(now + 0.15);
        }

        setIcon(weatherIconEl, ICONS.sun);
        setIcon(ledIconEl, ICONS.ledOff);
        setIcon(buzzerIconEl, ICONS.buzzerOff);
        setIcon(pollutionIconEl, ICONS.ok);

        if (desktopBeepEnabled) {
            window.addEventListener("pointerdown", unlockAudio, { once: true });
            window.addEventListener("keydown", unlockAudio, { once: true });
        }

        // Parallax disabled to reduce browser CPU/GPU usage on Raspberry Pi.

        function calculateAirQuality(tempC, humidity, mq135Ppm) {
            let tempScore = 0;
            let humidityScore = 0;
            let gasScore = 0;

            if (tempC >= 20 && tempC <= 24) {
                tempScore = 0;
            } else if (tempC < 20) {
                tempScore = Math.min(100, (20 - tempC) * 5);
            } else {
                tempScore = Math.min(100, (tempC - 24) * 5);
            }

            if (humidity >= 40 && humidity <= 60) {
                humidityScore = 0;
            } else if (humidity < 40) {
                humidityScore = Math.min(100, (40 - humidity) * 2);
            } else {
                humidityScore = Math.min(100, (humidity - 60) * 2);
            }

            if (mq135Ppm < 600) {
                gasScore = (mq135Ppm / 600) * 50;
            } else {
                gasScore = 50 + Math.min(50, (mq135Ppm - 600) / 14);
            }

            const penaltyScore = (tempScore + humidityScore + gasScore) / 3;
            const qualityScore = Math.max(0, Math.min(100, 100 - penaltyScore));
            return Math.round(qualityScore);
        }

        function getQualityLevel(score) {
            if (score >= 67) return { level: "good", color: "#33d17a", status: "Powietrze dobre", narrative: "Sloneczny tryb: stabilny mikroklimat" };
            if (score >= 34) return { level: "fair", color: "#f4b63d", status: "Powietrze srednie", narrative: "Uwaga: parametry poza optimum" };
            return { level: "poor", color: "#f15a5a", status: "Powietrze slabe", narrative: "Alarm: slaba jakosc powietrza" };
        }

        function updateCloudSyncUi(enabled) {
            cloudSyncToggleEl.checked = enabled;
            cloudSyncStateEl.textContent = enabled ? "Status: wlaczone" : "Status: wylaczone";
        }

        function updateBuzzerManualUi(enabled) {
            buzzerManualToggleEl.checked = enabled;
            buzzerManualStateEl.textContent = enabled ? "Tryb reczny: wlaczony" : "Tryb reczny: wylaczony";
        }

        function updateCloudUploadStatus(statusPayload) {
            const state = String(statusPayload?.state || "idle");
            const message = String(statusPayload?.message || "");
            cloudUploadPillEl.classList.remove("ok", "error");

            if (state === "ok") {
                cloudUploadPillEl.classList.add("ok");
                cloudUploadTextEl.textContent = "ThingSpeak OK";
                cloudUploadDetailEl.textContent = message ? `Szczegoly: ${message}` : "";
                return;
            }
            if (state === "error") {
                cloudUploadPillEl.classList.add("error");
                cloudUploadTextEl.textContent = "ThingSpeak blad";
                cloudUploadDetailEl.textContent = message ? `Szczegoly: ${message}` : "Brak odpowiedzi z API.";
                return;
            }
            if (state === "disabled") {
                cloudUploadTextEl.textContent = "Upload wylaczony";
                cloudUploadDetailEl.textContent = "";
                return;
            }

            cloudUploadTextEl.textContent = "Oczekiwanie na wysylke";
            cloudUploadDetailEl.textContent = "";
        }

        async function refreshStatus() {
            try {
                const response = await fetch("/api/status", { cache: "no-store" });
                if (!response.ok) {
                    return;
                }

                const payload = await response.json();
                if (typeof payload.cloud_sync_enabled === "boolean" && document.activeElement !== cloudSyncToggleEl) {
                    updateCloudSyncUi(payload.cloud_sync_enabled);
                }
                if (typeof payload.buzzer_manual_enabled === "boolean" && document.activeElement !== buzzerManualToggleEl) {
                    updateBuzzerManualUi(payload.buzzer_manual_enabled);
                }
                updateCloudUploadStatus(payload.cloud_upload);
                ledDotEl.style.background = payload.led.status_color;
                ledModeEl.textContent = String(payload.led.current_mode).toUpperCase();
                ledStateTextEl.textContent = `RED: ${payload.led.red_on ? "ON" : "OFF"} | GREEN: ${payload.led.green_on ? "ON" : "OFF"}`;
                const isGreenLed = String(payload.led.current_mode).toLowerCase() === "green";

                if (payload.temperature.available) {
                    temperatureCEl.textContent = `${payload.temperature.temperature_c.toFixed(2)} C`;
                    humidityPctEl.textContent = `Wilgotnosc: ${payload.temperature.humidity_pct.toFixed(2)} %`;
                    temperatureFEl.textContent = `${payload.temperature.temperature_f.toFixed(2)} F`;
                    temperatureFEl.classList.remove("error");
                } else {
                    temperatureCEl.textContent = "Brak danych";
                    humidityPctEl.textContent = "Wilgotnosc: -- %";
                    temperatureFEl.textContent = payload.temperature.error || "Brak odczytu";
                    temperatureFEl.classList.add("error");
                }

                buzzerStateEl.textContent = payload.buzzer.is_on ? "AKTYWNY" : "WYLACZONY";
                buzzerChipEl.classList.toggle("alert", payload.buzzer.is_on);
                buzzerChipEl.classList.toggle("pulse", payload.buzzer.is_on);
                buzzerChipEl.classList.toggle("active-shine", payload.buzzer.is_on);
                setIcon(buzzerIconEl, payload.buzzer.is_on ? ICONS.buzzerOn : ICONS.buzzerOff);
                buzzerChipTextEl.textContent = payload.buzzer.is_on ? "Buzzer wlaczony - miga" : "Buzzer wylaczony";

                ledChipEl.classList.toggle("green", isGreenLed);
                ledChipEl.classList.toggle("active-shine", isGreenLed);
                setIcon(ledIconEl, isGreenLed ? ICONS.ledOn : ICONS.ledOff);
                ledChipTextEl.textContent = isGreenLed ? "Div zielony aktywny" : "Div zielony nieaktywny";

                if (payload.mq135.available) {
                    displayedPpm = animateNumber(mq135PpmEl, displayedPpm, payload.mq135.ppm, {
                        decimals: 2,
                        durationMs: 680,
                        suffix: " ppm",
                    });
                    mq135VoltageEl.textContent = `Napiecie: ${payload.mq135.voltage.toFixed(3)} V`;
                    mq135RawEl.textContent = `RAW: ${payload.mq135.raw}`;
                    mq135ErrorEl.style.display = "none";

                    const highPpm = payload.mq135.ppm >= 1000;
                    pollutionChipEl.classList.toggle("alert", highPpm);
                    pollutionChipEl.classList.toggle("active-shine", highPpm);
                    setIcon(pollutionIconEl, highPpm ? ICONS.pollution : ICONS.ok);
                    pollutionTextEl.textContent = highPpm
                        ? `Ikona skazenia aktywna (${payload.mq135.ppm.toFixed(0)} ppm)`
                        : `PPM stabilne (${payload.mq135.ppm.toFixed(0)} ppm)`;

                    const isRain = payload.temperature.available && payload.temperature.humidity_pct >= 70;
                    document.body.dataset.rain = isRain ? "on" : "off";
                    weatherChipEl.classList.toggle("active-shine", isRain || String(document.body.dataset.aq) === "good");
                    setIcon(weatherIconEl, isRain ? ICONS.rain : ICONS.sun);
                    weatherTextEl.textContent = isRain
                        ? `Wilgotnosc ${payload.temperature.humidity_pct.toFixed(0)}% - efekt deszczu`
                        : "Dobre warunki - efekt slonca";

                    if (payload.temperature.available && payload.mq135.available) {
                        const qualityScore = calculateAirQuality(
                            payload.temperature.temperature_c,
                            payload.temperature.humidity_pct,
                            payload.mq135.ppm
                        );
                        const qualityInfo = getQualityLevel(qualityScore);

                        displayedScore = animateNumber(airQualityScoreEl, displayedScore, qualityScore, {
                            decimals: 0,
                            durationMs: 740,
                            suffix: " / 100",
                        });
                        airQualityBarEl.style.width = `${qualityScore}%`;
                        airQualityBarEl.style.background = qualityInfo.color;
                        airQualityLevelEl.textContent = `Status: ${qualityInfo.status}`;
                        qualityNarrativeEl.textContent = `Skan klimatu: ${qualityInfo.narrative}`;
                        if (lastAqLevel !== "poor" && qualityInfo.level === "poor") {
                            triggerAlarmKick();
                            playAlarmBeep();
                        }
                        lastAqLevel = qualityInfo.level;
                        document.body.dataset.aq = qualityInfo.level;
                    }
                } else {
                    displayedPpm = null;
                    displayedScore = null;
                    mq135PpmEl.textContent = "-- ppm";
                    mq135VoltageEl.textContent = "Napiecie: -- V";
                    mq135RawEl.textContent = "RAW: --";
                    mq135ErrorEl.textContent = payload.mq135.error || "Brak odczytu";
                    mq135ErrorEl.style.display = "block";
                    pollutionChipEl.classList.add("alert");
                    pollutionChipEl.classList.remove("active-shine");
                    setIcon(pollutionIconEl, ICONS.error);
                    pollutionTextEl.textContent = "Brak danych ppm / czujnik niedostepny";
                    document.body.dataset.rain = "off";
                    weatherChipEl.classList.remove("active-shine");
                    setIcon(weatherIconEl, ICONS.sun);
                    weatherTextEl.textContent = "Brak danych wilgotnosci dla efektu deszczu";
                    airQualityScoreEl.textContent = "-- / 100";
                    airQualityLevelEl.textContent = "Status: --";
                    qualityNarrativeEl.textContent = "Skan klimatu: brak danych MQ135";
                    lastAqLevel = "unknown";
                    document.body.dataset.aq = "unknown";
                }
            } catch {
                // Ignore transient network errors during polling.
            }
        }

        cloudSyncToggleEl.addEventListener("change", async (event) => {
            const enabled = Boolean(event.target.checked);
            cloudSyncToggleEl.disabled = true;
            try {
                const response = await fetch("/api/cloud-sync", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ enabled }),
                });
                if (!response.ok) {
                    return;
                }
                const payload = await response.json();
                if (typeof payload.enabled === "boolean") {
                    updateCloudSyncUi(payload.enabled);
                }
            } catch {
                // Ignore transient network errors while toggling.
            } finally {
                cloudSyncToggleEl.disabled = false;
            }
        });

        buzzerManualToggleEl.addEventListener("change", async (event) => {
            const enabled = Boolean(event.target.checked);
            buzzerManualToggleEl.disabled = true;
            try {
                const response = await fetch("/api/buzzer-manual", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ enabled }),
                });
                if (!response.ok) {
                    return;
                }
                const payload = await response.json();
                if (typeof payload.enabled === "boolean") {
                    updateBuzzerManualUi(payload.enabled);
                }
            } catch {
                // Ignore transient network errors while toggling.
            } finally {
                buzzerManualToggleEl.disabled = false;
            }
        });

        setInterval(refreshStatus, 2000);
    </script>
</body>
</html>
"""


@dataclass(slots=True)
class LedState:
    mode: str = "off"


@dataclass(slots=True)
class TemperatureSnapshot:
    available: bool
    temperature_c: float | None = None
    humidity_pct: float | None = None
    temperature_f: float | None = None
    error: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "temperature_c": self.temperature_c,
            "humidity_pct": self.humidity_pct,
            "temperature_f": self.temperature_f,
            "error": self.error,
        }


class LedController:
    def __init__(self, red_pin: int = 24, green_pin: int = 23) -> None:
        self._state = LedState()
        self._is_mock = LED is None
        if self._is_mock:
            self._red = None
            self._green = None
        else:
            self._red = LED(red_pin)
            self._green = LED(green_pin)
        self.set_mode("off")

    def set_mode(self, mode: str) -> None:
        mode = mode.lower()
        if mode not in {"red", "green", "yellow", "off"}:
            raise ValueError("Nieobslugiwany tryb LED")

        if not self._is_mock:
            if mode == "red":
                self._red.on()
                self._green.off()
            elif mode == "green":
                self._red.off()
                self._green.on()
            elif mode == "yellow":
                self._red.on()
                self._green.on()
            else:
                self._red.off()
                self._green.off()

        self._state.mode = mode

    def snapshot(self) -> dict[str, object]:
        mode_to_color = {
            "red": "#d7263d",
            "green": "#1f9d55",
            "yellow": "#e09f3e",
            "off": "#6b7280",
        }
        mode = self._state.mode
        red_on = mode in {"red", "yellow"}
        green_on = mode in {"green", "yellow"}
        return {
            "current_mode": mode,
            "red_on": red_on,
            "green_on": green_on,
            "status_color": mode_to_color[mode],
        }


class BuzzerController:
    def __init__(self, pin: int = 25) -> None:
        self._is_mock = Buzzer is None
        self._is_on = False
        if self._is_mock:
            self._buzzer = None
        else:
            self._buzzer = Buzzer(pin)
        self.off()

    def on(self) -> None:
        if not self._is_mock:
            self._buzzer.on()
        self._is_on = True

    def off(self) -> None:
        if not self._is_mock:
            self._buzzer.off()
        self._is_on = False

    def snapshot(self, threshold_c: float) -> dict[str, object]:
        return {
            "is_on": self._is_on,
            "threshold_c": threshold_c,
        }


class DHTSensor:
    def __init__(
        self,
        gpio_pin: int = 17,
        sensor_model: str = "dht11",
        retry_count: int = 5,
        retry_delay_seconds: float = 2.0,
    ) -> None:
        self._is_mock = board is None or adafruit_dht is None
        self._mock_temperature = 22.0
        self._mock_humidity = 48.0
        self._retry_count = max(1, retry_count)
        self._retry_delay_seconds = max(0.1, retry_delay_seconds)

        if self._is_mock:
            self._device = None
            return

        board_pin_name = f"D{gpio_pin}"
        board_pin = getattr(board, board_pin_name, None)
        if board_pin is None:
            raise ValueError(f"Nieobslugiwany GPIO dla DHT: {gpio_pin}")

        normalized_model = sensor_model.lower()
        if normalized_model == "dht11":
            self._device = adafruit_dht.DHT11(board_pin, use_pulseio=False)
        elif normalized_model == "dht22":
            self._device = adafruit_dht.DHT22(board_pin, use_pulseio=False)
        else:
            raise ValueError("DHT_MODEL musi byc rowne dht11 albo dht22")

    def read_temperature(self) -> TemperatureSnapshot:
        if self._is_mock:
            self._mock_temperature = max(
                16.0,
                min(34.0, self._mock_temperature + random.uniform(-0.4, 0.4)),
            )
            self._mock_humidity = max(
                25.0,
                min(85.0, self._mock_humidity + random.uniform(-1.2, 1.2)),
            )
            temp_c = self._mock_temperature
            humidity = self._mock_humidity
            temp_f = temp_c * 9.0 / 5.0 + 32.0
            return TemperatureSnapshot(
                available=True,
                temperature_c=temp_c,
                humidity_pct=humidity,
                temperature_f=temp_f,
            )

        last_error = "Brak danych z DHT."
        for attempt in range(1, self._retry_count + 1):
            try:
                temp_c = self._device.temperature
                humidity = self._device.humidity
                if temp_c is not None and humidity is not None:
                    temp_f = temp_c * 9.0 / 5.0 + 32.0
                    return TemperatureSnapshot(
                        available=True,
                        temperature_c=temp_c,
                        humidity_pct=humidity,
                        temperature_f=temp_f,
                    )

                last_error = "DHT zwrocil niepelne dane."
            except RuntimeError as exc:
                last_error = f"Blad odczytu DHT: {exc}"
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)

            if attempt < self._retry_count:
                time.sleep(self._retry_delay_seconds)

        return TemperatureSnapshot(available=False, error=last_error)


class MQ135Sensor:
    def __init__(
        self,
        i2c_address: int = 0x48,
        channel: int = 0,
        retry_count: int = 3,
        retry_delay_seconds: float = 0.2,
    ) -> None:
        self._is_mock = board is None or busio is None or ADS is None or AnalogIn is None
        self._mock_ppm = 400.0
        self._retry_count = max(1, retry_count)
        self._retry_delay_seconds = max(0.1, retry_delay_seconds)
        self._channel = channel

        if self._is_mock:
            self._ads = None
            self._channel_obj = None
            return

        try:
            i2c = busio.I2C(board.SCL, board.SDA)
            self._ads = ADS.ADS1115(i2c, address=i2c_address)
            self._ads.gain = 1
            normalized_channel = max(0, min(3, int(channel)))
            self._channel_obj = self._create_channel(self._ads, normalized_channel)
        except Exception as exc:
            print(f"DEBUG MQ135: Blad inicjalizacji ADS1115: {exc}")
            self._is_mock = True
            self._ads = None
            self._channel_obj = None

    @staticmethod
    def _create_channel(ads_device, channel: int):
        # Support multiple adafruit_ads1x15 versions exposing different channel constants.
        candidate_names = (
            f"P{channel}",
            f"A{channel}",
            f"AIN{channel}",
            f"IN{channel}",
        )
        for name in candidate_names:
            pin = getattr(ADS, name, None)
            if pin is None:
                continue
            try:
                return AnalogIn(ads_device, pin)
            except Exception:
                continue

        # Final fallback for builds where AnalogIn accepts integer channel index.
        try:
            return AnalogIn(ads_device, channel)
        except Exception as exc:
            raise RuntimeError(
                f"Nie mozna ustawic kanalu ADS1115={channel}."
            ) from exc

    def read_ppm(self) -> dict[str, object]:
        if self._is_mock:
            return {
                "available": False,
                "ppm": None,
                "raw": None,
                "voltage": None,
                "error": "ADS1115 (0x48) nie znaleziony na I2C. Sprawdź połączenie.",
            }

        last_error = "Brak danych z MQ135."
        for attempt in range(1, self._retry_count + 1):
            try:
                if self._channel_obj is not None:
                    raw_value = self._channel_obj.value
                    voltage = self._channel_obj.voltage
                    ppm = voltage * 204.8  # przybliżona konwersja V -> ppm
                    return {
                        "available": True,
                        "ppm": round(ppm, 2),
                        "raw": raw_value,
                        "voltage": round(voltage, 3),
                        "error": "",
                    }
                last_error = "Brak kanału MQ135."
            except Exception as exc:
                last_error = f"Blad odczytu MQ135: {exc}"

            if attempt < self._retry_count:
                time.sleep(self._retry_delay_seconds)

        return {
            "available": False,
            "ppm": None,
            "raw": None,
            "voltage": None,
            "error": last_error,
        }


class AirQualityMonitor:
    def __init__(self, led_controller: LedController, buzzer_controller: BuzzerController) -> None:
        self._led = led_controller
        self._buzzer = buzzer_controller
        self._last_score = 0

    def evaluate(
        self,
        temp_c: float | None,
        humidity: float | None,
        mq135_ppm: float | None,
    ) -> dict[str, object]:
        """Ocenia jakość powietrza (0-100, gdzie 100 = najlepsze)."""
        if temp_c is None or humidity is None or mq135_ppm is None:
            return {
                "score": 0,
                "level": "unknown",
                "color": "#6b7280",
            }

        # Oceny cząstkowe (0-100)
        temp_score = self._score_temperature(temp_c)
        humidity_score = self._score_humidity(humidity)
        gas_score = self._score_gas(mq135_ppm)

        # Srednia kar i transformacja do skali jakosci: 100 = najlepsze, 0 = najgorsze.
        penalty_score = (temp_score + humidity_score + gas_score) / 3.0
        penalty_score = max(0, min(100, penalty_score))
        overall_score = 100.0 - penalty_score
        self._last_score = overall_score

        # Określ poziom i akcje
        if overall_score >= 67:
            level = "good"
            color = "green"
            led_mode = "green"
            buzzer_on = True
        elif overall_score >= 34:
            level = "fair"
            color = "yellow"
            led_mode = "yellow"
            buzzer_on = False
        else:
            level = "poor"
            color = "red"
            led_mode = "red"
            buzzer_on = True

        # Zmień LED automatyczne
        try:
            self._led.set_mode(led_mode)
        except Exception:
            pass

        # Włącz/wyłącz buzzer na podstawie jakości
        if buzzer_on:
            self._buzzer.on()
        else:
            self._buzzer.off()

        return {
            "score": round(overall_score, 1),
            "level": level,
            "color": color,
        }

    @staticmethod
    def _score_temperature(temp_c: float) -> float:
        """Ideał 20-24°C."""
        if 20 <= temp_c <= 24:
            return 0.0
        elif temp_c < 20:
            return min(100.0, (20 - temp_c) * 5)
        else:
            return min(100.0, (temp_c - 24) * 5)

    @staticmethod
    def _score_humidity(humidity: float) -> float:
        """Ideał 40-60%."""
        if 40 <= humidity <= 60:
            return 0.0
        elif humidity < 40:
            return min(100.0, (40 - humidity) * 2)
        else:
            return min(100.0, (humidity - 60) * 2)

    @staticmethod
    def _score_gas(ppm: float) -> float:
        """Ideał < 600 ppm."""
        if ppm < 600:
            return (ppm / 600) * 50
        else:
            return 50 + min(50.0, (ppm - 600) / 14)


class TemperatureMonitor:
    def __init__(
        self,
        sensor: DHTSensor,
        buzzer: BuzzerController,
        threshold_c: float,
        interval_seconds: float = 1.0,
        filter_window_samples: int = 5,
        filter_method: str = "median",
    ) -> None:
        self._sensor = sensor
        self._buzzer = buzzer
        self._threshold_c = threshold_c
        self._interval_seconds = interval_seconds
        self._filter_window_samples = max(1, filter_window_samples)
        normalized_filter_method = filter_method.lower().strip()
        self._filter_method = normalized_filter_method if normalized_filter_method in {"median", "mean"} else "median"
        self._latest = TemperatureSnapshot(available=False, error="Oczekiwanie na pierwszy odczyt.")
        self._temperature_samples: deque[float] = deque(maxlen=self._filter_window_samples)
        self._humidity_samples: deque[float] = deque(maxlen=self._filter_window_samples)
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self.refresh_once()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def refresh_once(self) -> None:
        snapshot = self._sensor.read_temperature()
        with self._lock:
            self._latest = snapshot
            if (
                snapshot.available
                and snapshot.temperature_c is not None
                and snapshot.humidity_pct is not None
            ):
                self._temperature_samples.append(float(snapshot.temperature_c))
                self._humidity_samples.append(float(snapshot.humidity_pct))

    def latest(self) -> TemperatureSnapshot:
        with self._lock:
            latest = TemperatureSnapshot(
                available=self._latest.available,
                temperature_c=self._latest.temperature_c,
                humidity_pct=self._latest.humidity_pct,
                temperature_f=self._latest.temperature_f,
                error=self._latest.error,
            )
            temperature_samples = list(self._temperature_samples)
            humidity_samples = list(self._humidity_samples)

        if not latest.available or not temperature_samples or not humidity_samples:
            return latest

        filtered_temp_c = self._aggregate_samples(temperature_samples)
        filtered_humidity_pct = self._aggregate_samples(humidity_samples)
        filtered_temp_f = filtered_temp_c * 9.0 / 5.0 + 32.0

        return TemperatureSnapshot(
            available=True,
            temperature_c=round(filtered_temp_c, 2),
            humidity_pct=round(filtered_humidity_pct, 2),
            temperature_f=round(filtered_temp_f, 2),
            error="",
        )

    def _aggregate_samples(self, samples: list[float]) -> float:
        if self._filter_method == "mean":
            return float(fmean(samples))
        return float(median(samples))

    def buzzer_snapshot(self) -> dict[str, object]:
        return self._buzzer.snapshot(self._threshold_c)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self.refresh_once()
            self._stop_event.wait(self._interval_seconds)


class ThingSpeakUploader:
    def __init__(
        self,
        api_key: str,
        interval_seconds: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._interval_seconds = interval_seconds
        self._temperature_monitor: TemperatureMonitor | None = None
        self._mq135_sensor: MQ135Sensor | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._enabled = True
        self._lock = threading.Lock()
        self._last_upload_state = "idle"
        self._last_upload_message = "Oczekiwanie na pierwsza wysylke."
        self._url = "https://api.thingspeak.com/update"

    def set_monitor(self, monitor: TemperatureMonitor) -> None:
        self._temperature_monitor = monitor

    def set_mq135_sensor(self, sensor: MQ135Sensor) -> None:
        self._mq135_sensor = sensor

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._enabled = bool(enabled)

    def is_enabled(self) -> bool:
        with self._lock:
            return self._enabled

    def get_upload_status(self) -> dict[str, str]:
        with self._lock:
            if not self._enabled:
                return {
                    "state": "disabled",
                    "message": "Wysylanie do chmury jest wylaczone.",
                }
            return {
                "state": self._last_upload_state,
                "message": self._last_upload_message,
            }

    def _set_upload_status(self, state: str, message: str) -> None:
        with self._lock:
            self._last_upload_state = state
            self._last_upload_message = message

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                if not self.is_enabled():
                    self._stop_event.wait(self._interval_seconds)
                    continue
                if self._temperature_monitor:
                    snapshot = self._temperature_monitor.latest()
                    if snapshot.available and snapshot.temperature_c is not None and snapshot.humidity_pct is not None:
                        payload = {
                            "api_key": self._api_key,
                            "field1": round(snapshot.temperature_c, 2),
                            "field2": round(snapshot.humidity_pct, 2),
                        }
                        if self._mq135_sensor is not None:
                            mq135_data = self._mq135_sensor.read_ppm()
                            ppm = mq135_data.get("ppm")
                            if mq135_data.get("available") and ppm is not None:
                                payload["field3"] = round(float(ppm), 2)
                        response = requests.post(self._url, data=payload, timeout=5)
                        if response.ok:
                            self._set_upload_status("ok", f"HTTP {response.status_code}")
                        else:
                            self._set_upload_status(
                                "error",
                                f"HTTP {response.status_code}: {response.text[:80]}",
                            )
                    else:
                        self._set_upload_status("error", "Brak kompletnych danych do wysylki.")
            except Exception:
                self._set_upload_status("error", "Wyjatek podczas wysylki do ThingSpeak.")

            self._stop_event.wait(self._interval_seconds)


def create_app() -> Flask:
    app = Flask(__name__)
    controller = LedController(
        red_pin=int(os.getenv("LED_RED_PIN", "24")),
        green_pin=int(os.getenv("LED_GREEN_PIN", "23")),
    )
    sensor = DHTSensor(
        gpio_pin=int(os.getenv("DHT_GPIO_PIN", "17")),
        sensor_model=os.getenv("DHT_MODEL", "dht11"),
        retry_count=int(os.getenv("DHT_RETRY_COUNT", "5")),
        retry_delay_seconds=float(os.getenv("DHT_RETRY_DELAY_SECONDS", "2")),
    )
    buzzer = BuzzerController(pin=int(os.getenv("BUZZER_PIN", "16")))
    monitor = TemperatureMonitor(
        sensor=sensor,
        buzzer=buzzer,
        threshold_c=float(os.getenv("BUZZER_THRESHOLD_C", "24")),
        interval_seconds=float(os.getenv("TEMPERATURE_POLL_INTERVAL_SECONDS", "1")),
        filter_window_samples=int(os.getenv("SENSOR_FILTER_WINDOW_SAMPLES", "5")),
        filter_method=os.getenv("SENSOR_FILTER_METHOD", "median"),
    )
    monitor.start()

    mq135 = MQ135Sensor(
        i2c_address=int(os.getenv("MQ135_I2C_ADDRESS", "0x48"), 0),
        channel=int(os.getenv("MQ135_CHANNEL", "0")),
    )

    uploader = ThingSpeakUploader(
        api_key=os.getenv("THINGSPEAK_API_KEY", "YO5QJ15G1DQ3BAQ3"),
        interval_seconds=float(os.getenv("THINGSPEAK_INTERVAL_SECONDS", "30")),
    )
    uploader.set_monitor(monitor)
    uploader.set_mq135_sensor(mq135)
    uploader.start()

    air_quality = AirQualityMonitor(controller, buzzer)
    buzzer_manual_state = {"enabled": False}

    @app.get("/")
    def index():
        temperature = monitor.latest()
        buzzer_state = monitor.buzzer_snapshot()
        return render_template_string(
            HTML,
            **controller.snapshot(),
            temperature_available=temperature.available,
            temperature_c=temperature.temperature_c,
            humidity_pct=temperature.humidity_pct,
            temperature_f=temperature.temperature_f,
            temperature_error=temperature.error,
            buzzer_on=buzzer_state["is_on"],
            buzzer_threshold_c=buzzer_state["threshold_c"],
        )

    @app.get("/api/status")
    def api_status():
        temperature = monitor.latest()
        mq135_data = mq135.read_ppm()

        # Ocena jakości powietrza
        quality_score = air_quality.evaluate(
            temperature.temperature_c,
            temperature.humidity_pct,
            mq135_data.get("ppm"),
        )

        if buzzer_manual_state["enabled"]:
            buzzer.on()

        return jsonify(
            {
                "led": controller.snapshot(),
                "temperature": temperature.to_dict(),
                "buzzer": monitor.buzzer_snapshot(),
                "mq135": mq135_data,
                "air_quality": quality_score,
                "cloud_sync_enabled": uploader.is_enabled(),
                "cloud_upload": uploader.get_upload_status(),
                "buzzer_manual_enabled": buzzer_manual_state["enabled"],
            }
        )

    @app.post("/api/cloud-sync")
    def api_cloud_sync_toggle():
        payload = request.get_json(silent=True) or {}
        raw_enabled = payload.get("enabled")

        if isinstance(raw_enabled, bool):
            enabled = raw_enabled
        elif isinstance(raw_enabled, str):
            enabled = raw_enabled.strip().lower() in {"1", "true", "yes", "on"}
        elif isinstance(raw_enabled, (int, float)):
            enabled = bool(raw_enabled)
        else:
            enabled = uploader.is_enabled()

        uploader.set_enabled(enabled)
        return jsonify({"enabled": uploader.is_enabled()})

    @app.post("/api/buzzer-manual")
    def api_buzzer_manual_toggle():
        payload = request.get_json(silent=True) or {}
        raw_enabled = payload.get("enabled")

        if isinstance(raw_enabled, bool):
            enabled = raw_enabled
        elif isinstance(raw_enabled, str):
            enabled = raw_enabled.strip().lower() in {"1", "true", "yes", "on"}
        elif isinstance(raw_enabled, (int, float)):
            enabled = bool(raw_enabled)
        else:
            enabled = buzzer_manual_state["enabled"]

        buzzer_manual_state["enabled"] = enabled
        if enabled:
            buzzer.on()
        return jsonify({"enabled": buzzer_manual_state["enabled"]})

    return app


app = create_app()


if __name__ == "__main__":
    app.run(
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8080")),
        debug=False,
    )

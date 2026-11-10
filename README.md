# Procurement Monitor Demo

A Python portfolio demo of a tool that screens public tenders against configurable criteria. The production workflow monitors procurement portals and sends a daily email digest at 08:30 with matched tenders and reasons.

This demo reuses the TED notice parser and keyword matcher. It runs offline with fictional notices and a sample scoring rule. The resulting digest appears in the terminal.

## Run the demo

Use Python 3.11 or later. From this folder, run:

    python main.py

The software notice scores 80/100 because it matches the keyword “software.” The office furniture notice is filtered out. See [the sample digest](sample-alert.md) for the expected output.

## How it works

1. The TED parser turns notice data into a common tender record.
2. The matcher applies keyword and procurement code rules from [the sample CSV](config/default_keywords.csv).
3. The demo prints the relevance score and the signals that triggered each match.

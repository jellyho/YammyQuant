# Information layer

Non-price inputs — the biggest edge for stocks. The key idea: **collection is
free** (keyless public sources) and **judgement is free too** (the operator,
Claude Code, reads the items and decides). No paid sentiment API.

```
feeds/  →  news table (state DB)  →  yq news / yq brief  →  you decide
```

<div class="grid cards" markdown>

-   :material-rss: **News (RSS)**

    Keyless RSS/Atom reader tags watchlist symbols and stores headlines.

-   :material-emoticon-outline: **Sentiment**

    A keyword scorer (EN + KR finance terms) auto-tags each item; you can override.

-   :material-file-document-outline: **Disclosures (DART)**

    전자공시 filings for Korean corporates (needs free `DART_API_KEY`).

-   :material-finance: **Fundamentals (KIS)**

    Stock price + PER / PBR / EPS / BPS / market cap via 한국투자증권.

</div>

## Collecting & reading news

```bash
yq news --collect                 # pull RSS, tag watchlist, score sentiment
yq news BTCUSDT                    # list stored news for a symbol
```

`collect_news` fetches each configured feed, tags items whose headline matches a
watchlist symbol (or its keywords), scores sentiment, and stores them deduped on
URL. Watchlist hits also fire a notification.

!!! note "Configure sources without editing code"
    Defaults live in `yammyquant/feeds/sources.py`, but you can override or extend
    them via state settings `news_sources` and `news_keywords`.

## Research brief

The brief is built for the operator to read and form a decision:

```bash
yq brief 005930 --exchange kis
```

```json
{
  "ticker": "005930",
  "price": 70000.0,
  "features": { "rsi_14": 58.2, "realized_vol_20": 0.21, ... },
  "news": [ { "title": "...", "sentiment": 0.5, "source": "..." } ],
  "news_sentiment": 0.32,
  "fundamentals": { "per": 12.5, "pbr": 1.3, "eps": 5600, ... },
  "position": null
}
```

## Disclosures (DART / 전자공시)

```bash
yq disclosures 00126380 --symbol 005930
```

Fetches recent regulatory filings for a company by its 8-digit DART `corp_code`
and stores them in the news table. Requires a free `DART_API_KEY` from
[opendart.fss.or.kr](https://opendart.fss.or.kr).

## Sentiment as a gate

The keyword scorer returns a value in roughly `[-1, 1]`. Set the `sentiment_gate`
state setting to have `yq decide` **veto entries** when recent news for a symbol is
strongly negative:

```bash
yq risk set sentiment_gate=-0.5     # skip BUY when avg sentiment < -0.5
```

The real judgement, though, is yours: read `yq news` / `yq brief` and decide.

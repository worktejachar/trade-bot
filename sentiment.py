# -*- coding: utf-8 -*-
"""
GX TradeIntel - News Sentiment Engine
=======================================
Fetches financial news and uses Claude API for:
- Sentiment analysis (bullish/bearish/neutral)
- Market impact scoring (HIGH/MEDIUM/LOW)
- Trading signal augmentation
"""

import logging
import json
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass

import requests

import config

logger = logging.getLogger("GXTradeIntel.News")


@dataclass
class NewsItem:
    title: str
    source: str
    url: str
    published: str
    sentiment: str = "neutral"      # bullish / bearish / neutral
    impact: str = "LOW"             # HIGH / MEDIUM / LOW
    score: float = 0.0              # -1.0 to +1.0
    summary: str = ""
    affects: List[str] = None       # ["NIFTY", "BANKNIFTY", "RELIANCE"]

    def __post_init__(self):
        if self.affects is None:
            self.affects = []


class NewsSentimentEngine:
    """Fetches and analyzes financial news for trading signals."""

    # Free RSS / API sources for Indian market news
    NEWS_SOURCES = [
        {
            "name": "MoneyControl",
            "url": "https://www.moneycontrol.com/rss/marketreports.xml",
            "type": "rss",
        },
        {
            "name": "ET Markets",
            "url": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
            "type": "rss",
        },
        {
            "name": "LiveMint",
            "url": "https://www.livemint.com/rss/markets",
            "type": "rss",
        },
    ]

    def __init__(self):
        self.cached_news: List[NewsItem] = []
        self.last_fetch: Optional[datetime] = None
        self.fetch_interval = timedelta(minutes=10)

    def fetch_news(self, max_items: int = 20) -> List[NewsItem]:
        """Fetch news from all RSS sources."""
        all_news = []

        for source in self.NEWS_SOURCES:
            try:
                items = self._fetch_rss(source["url"], source["name"], max_items=8)
                all_news.extend(items)
            except Exception as e:
                logger.warning(f"Failed to fetch from {source['name']}: {e}")

        # Deduplicate by title similarity
        seen_titles = set()
        unique_news = []
        for item in all_news:
            key = item.title[:50].lower()
            if key not in seen_titles:
                seen_titles.add(key)
                unique_news.append(item)

        self.cached_news = unique_news[:max_items]
        self.last_fetch = datetime.now()

        logger.info(f"📰 Fetched {len(self.cached_news)} news items from {len(self.NEWS_SOURCES)} sources")
        return self.cached_news

    def _fetch_rss(self, url: str, source_name: str, max_items: int = 10) -> List[NewsItem]:
        """Parse RSS feed into NewsItems."""
        items = []

        try:
            resp = requests.get(url, timeout=10, headers={
                "User-Agent": "GXTradeIntel/1.0"
            })
            content = resp.text

            # Simple XML parsing (no lxml dependency needed)
            # Extract <item> blocks
            item_blocks = re.findall(r"<item>(.*?)</item>", content, re.DOTALL)

            for block in item_blocks[:max_items]:
                title_match = re.search(r"<title><!\[CDATA\[(.*?)\]\]>|<title>(.*?)</title>", block)
                link_match = re.search(r"<link>(.*?)</link>", block)
                pub_match = re.search(r"<pubDate>(.*?)</pubDate>", block)

                title = ""
                if title_match:
                    title = title_match.group(1) or title_match.group(2) or ""
                    title = title.strip()

                link = link_match.group(1).strip() if link_match else ""
                pub_date = pub_match.group(1).strip() if pub_match else ""

                if title:
                    items.append(NewsItem(
                        title=title,
                        source=source_name,
                        url=link,
                        published=pub_date,
                    ))

        except Exception as e:
            logger.warning(f"RSS parse error for {source_name}: {e}")

        return items

    def analyze_sentiment_batch(self, news_items: List[NewsItem]) -> List[NewsItem]:
        """Use Claude API to analyze sentiment of news batch."""

        if not news_items:
            return []

        # Build the prompt
        titles = "\n".join([f"{i+1}. {item.title}" for i, item in enumerate(news_items)])

        prompt = f"""Analyze these Indian stock market news headlines for trading sentiment.
For each headline, return a JSON array with:
- index (1-based)
- sentiment: "bullish", "bearish", or "neutral"
- impact: "HIGH", "MEDIUM", or "LOW" (how much it moves Nifty/BankNifty)
- score: -1.0 to +1.0 (negative=bearish, positive=bullish)
- affects: array of affected instruments ["NIFTY", "BANKNIFTY", "RELIANCE", etc.]

Headlines:
{titles}

Return ONLY valid JSON array. No explanation. Example:
[{{"index":1,"sentiment":"bullish","impact":"HIGH","score":0.8,"affects":["NIFTY","BANKNIFTY"]}}]"""

        try:
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": config.ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 2000,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=30,
            )

            if response.status_code != 200:
                logger.warning(f"Claude API error: {response.status_code}")
                return self._fallback_sentiment(news_items)

            data = response.json()
            text = data["content"][0]["text"]

            # Parse JSON response
            # Clean potential markdown wrapping
            text = text.strip()
            if text.startswith("```"):
                text = re.sub(r"```json?\n?", "", text)
                text = text.rstrip("`").strip()

            results = json.loads(text)

            for result in results:
                idx = result.get("index", 0) - 1
                if 0 <= idx < len(news_items):
                    news_items[idx].sentiment = result.get("sentiment", "neutral")
                    news_items[idx].impact = result.get("impact", "LOW")
                    news_items[idx].score = result.get("score", 0.0)
                    news_items[idx].affects = result.get("affects", [])

            logger.info(f"🧠 Sentiment analyzed for {len(results)} headlines via Claude")
            return news_items

        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error from Claude: {e}")
            return self._fallback_sentiment(news_items)
        except Exception as e:
            logger.warning(f"Sentiment analysis error: {e}")
            return self._fallback_sentiment(news_items)

    def _fallback_sentiment(self, news_items: List[NewsItem]) -> List[NewsItem]:
        """Keyword-based fallback sentiment when API is unavailable."""
        bullish_words = [
            "rally", "surge", "jump", "gain", "high", "bull", "buy", "positive",
            "recovery", "growth", "profit", "upgrade", "breakout", "soar",
            "record", "boom", "strong", "upbeat", "optimism", "rise",
        ]
        bearish_words = [
            "crash", "fall", "drop", "loss", "bear", "sell", "negative",
            "decline", "fear", "recession", "downgrade", "plunge", "tank",
            "weak", "concern", "risk", "panic", "slump", "cut", "war",
        ]

        for item in news_items:
            title_lower = item.title.lower()
            bull_count = sum(1 for w in bullish_words if w in title_lower)
            bear_count = sum(1 for w in bearish_words if w in title_lower)

            if bull_count > bear_count:
                item.sentiment = "bullish"
                item.score = min(0.3 * bull_count, 1.0)
            elif bear_count > bull_count:
                item.sentiment = "bearish"
                item.score = max(-0.3 * bear_count, -1.0)
            else:
                item.sentiment = "neutral"
                item.score = 0.0

            # Impact based on keywords
            high_impact = ["rbi", "fed", "rate", "crude", "fii", "war", "gdp", "inflation", "tariff"]
            if any(w in title_lower for w in high_impact):
                item.impact = "HIGH"
            elif bull_count + bear_count >= 2:
                item.impact = "MEDIUM"
            else:
                item.impact = "LOW"

            item.affects = ["NIFTY"]  # Default

        logger.info(f"📰 Fallback sentiment for {len(news_items)} items (keyword-based)")
        return news_items

    def get_market_sentiment_score(self) -> Dict:
        """Aggregate sentiment score across all news."""
        if not self.cached_news:
            return {"score": 0, "label": "NEUTRAL", "bullish": 0, "bearish": 0, "neutral": 0}

        bull = sum(1 for n in self.cached_news if n.sentiment == "bullish")
        bear = sum(1 for n in self.cached_news if n.sentiment == "bearish")
        neut = sum(1 for n in self.cached_news if n.sentiment == "neutral")

        # Weighted average (HIGH impact = 3x, MEDIUM = 2x, LOW = 1x)
        weight_map = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
        weighted_score = sum(
            n.score * weight_map.get(n.impact, 1) for n in self.cached_news
        )
        total_weight = sum(weight_map.get(n.impact, 1) for n in self.cached_news)
        avg_score = weighted_score / total_weight if total_weight > 0 else 0

        if avg_score > 0.2:
            label = "BULLISH"
        elif avg_score < -0.2:
            label = "BEARISH"
        else:
            label = "NEUTRAL"

        return {
            "score": round(avg_score, 3),
            "label": label,
            "bullish": bull,
            "bearish": bear,
            "neutral": neut,
            "total": len(self.cached_news),
        }

    def get_high_impact_news(self) -> List[NewsItem]:
        """Return only HIGH impact news items."""
        return [n for n in self.cached_news if n.impact == "HIGH"]

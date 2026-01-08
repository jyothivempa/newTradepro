"""
TradeEdge Pro - News Sentiment Analysis
Skip stocks with negative news using Google News RSS + TextBlob
"""
import re
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import feedparser
from textblob import TextBlob

from app.utils.logger import get_logger

logger = get_logger(__name__)

# Cache for news sentiment
_sentiment_cache: Dict[str, dict] = {}
_cache_ttl = 3600  # 1 hour


def _get_google_news_rss(query: str, days: int = 3) -> List[dict]:
    """Fetch news from Google News RSS feed"""
    try:
        # Google News RSS URL
        url = f"https://news.google.com/rss/search?q={query}+stock+india&hl=en-IN&gl=IN&ceid=IN:en"
        
        feed = feedparser.parse(url)
        
        if not feed.entries:
            return []
        
        # Get recent entries
        cutoff = datetime.now() - timedelta(days=days)
        articles = []
        
        for entry in feed.entries[:10]:  # Limit to 10 articles
            try:
                # Parse published date
                published = datetime(*entry.published_parsed[:6])
                
                if published >= cutoff:
                    articles.append({
                        "title": entry.title,
                        "link": entry.link,
                        "published": published.isoformat(),
                        "source": entry.get("source", {}).get("title", "Unknown"),
                    })
            except Exception:
                continue
        
        return articles
    
    except Exception as e:
        logger.warning(f"Failed to fetch news for {query}: {e}")
        return []


def analyze_sentiment(text: str) -> float:
    """
    Analyze sentiment of text using TextBlob.
    Returns: -1.0 (very negative) to +1.0 (very positive)
    """
    try:
        blob = TextBlob(text)
        return blob.sentiment.polarity
    except Exception:
        return 0.0


def _detect_negative_keywords(text: str) -> bool:
    """Check for explicitly negative keywords"""
    negative_keywords = [
        "fraud", "scam", "investigation", "raid", "warning",
        "downgrade", "sell rating", "loss", "crash", "plunge",
        "default", "bankruptcy", "sebi notice", "penalty",
        "block deal", "promoter selling", "resignation",
        "profit warning", "revenue miss", "layoffs", "strike"
    ]
    
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in negative_keywords)


def get_stock_sentiment(symbol: str, stock_name: str = "") -> dict:
    """
    Get sentiment analysis for a stock.
    
    Returns:
        {
            "symbol": str,
            "sentiment": float,  # -1 to +1
            "label": str,  # "positive", "neutral", "negative"
            "articleCount": int,
            "hasNegativeNews": bool,
            "articles": list
        }
    """
    # Check cache
    cache_key = symbol
    if cache_key in _sentiment_cache:
        cached = _sentiment_cache[cache_key]
        if datetime.now().timestamp() - cached.get("timestamp", 0) < _cache_ttl:
            return cached["data"]
    
    # Build search query
    search_query = f"{symbol}"
    if stock_name:
        # Add company name without common suffixes
        clean_name = re.sub(r'\s*(Ltd\.?|Limited|Inc\.?|Corp\.?)$', '', stock_name, flags=re.I)
        search_query = f"{symbol} OR {clean_name}"
    
    # Fetch news
    articles = _get_google_news_rss(search_query)
    
    if not articles:
        result = {
            "symbol": symbol,
            "sentiment": 0.0,
            "label": "neutral",
            "articleCount": 0,
            "hasNegativeNews": False,
            "articles": [],
        }
        _sentiment_cache[cache_key] = {"data": result, "timestamp": datetime.now().timestamp()}
        return result
    
    # Analyze sentiment
    sentiments = []
    has_explicit_negative = False
    
    for article in articles:
        title = article["title"]
        sentiment = analyze_sentiment(title)
        sentiments.append(sentiment)
        
        # Check for explicit negative keywords
        if _detect_negative_keywords(title):
            has_explicit_negative = True
            article["flagged"] = True
        else:
            article["flagged"] = False
        
        article["sentiment"] = round(sentiment, 2)
    
    # Calculate average sentiment
    avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0
    
    # Determine label
    if avg_sentiment <= -0.2 or has_explicit_negative:
        label = "negative"
    elif avg_sentiment >= 0.2:
        label = "positive"
    else:
        label = "neutral"
    
    result = {
        "symbol": symbol,
        "sentiment": round(avg_sentiment, 2),
        "label": label,
        "articleCount": len(articles),
        "hasNegativeNews": has_explicit_negative or avg_sentiment < -0.3,
        "articles": articles[:5],  # Return top 5
    }
    
    # Cache result
    _sentiment_cache[cache_key] = {"data": result, "timestamp": datetime.now().timestamp()}
    
    logger.info(f"News sentiment for {symbol}: {label} ({avg_sentiment:.2f})")
    return result


def should_skip_stock(symbol: str, stock_name: str = "") -> tuple[bool, str]:
    """
    Check if stock should be skipped due to negative news.
    
    Returns:
        (should_skip, reason)
    """
    try:
        sentiment = get_stock_sentiment(symbol, stock_name)
        
        if sentiment["hasNegativeNews"]:
            return True, f"Negative news detected (sentiment: {sentiment['sentiment']:.2f})"
        
        return False, ""
    
    except Exception as e:
        logger.warning(f"Sentiment check failed for {symbol}: {e}")
        return False, ""  # Don't skip on error


def get_sentiment_penalty(symbol: str, stock_name: str = "") -> int:
    """
    Get score penalty based on news sentiment.
    
    Returns:
        0 (neutral/positive) to -30 (very negative)
    """
    try:
        sentiment = get_stock_sentiment(symbol, stock_name)
        
        if sentiment["hasNegativeNews"]:
            return -30
        
        if sentiment["sentiment"] < -0.2:
            return -15
        
        if sentiment["sentiment"] > 0.3:
            return 10  # Bonus for positive news
        
        return 0
    
    except Exception:
        return 0


def clear_cache():
    """Clear sentiment cache"""
    global _sentiment_cache
    _sentiment_cache = {}
    logger.info("Sentiment cache cleared")

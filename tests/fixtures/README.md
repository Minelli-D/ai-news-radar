# Test fixtures

Real responses captured on **2026-09-25** (Hugging Face: **2026-09-29**) with the collector's
User-Agent, then trimmed so the repository never republishes article bodies (see the content
rules in the main README).

| File | Captured from | Trimming |
|---|---|---|
| `anthropic_news.html` | https://www.anthropic.com/news | Embedded CMS data cut to the 8 newest posts (re-chunked into 3 `self.__next_f.push` scripts) |
| `openai_news_rss.xml` | https://openai.com/news/rss.xml | First 8 of 1,229 items |
| `deepseek_sitemap.xml` | https://api-docs.deepseek.com/sitemap.xml | none |
| `deepseek_news_latest.html` | https://api-docs.deepseek.com/news/news260910 | Article body replaced by a placeholder; head + sidebar kept |
| `google_ai_rss.xml` | https://blog.google/innovation-and-ai/technology/ai/rss/ | First 6 of 20 items |
| `deepmind_rss.xml` | https://deepmind.google/blog/rss.xml | First 8 of 100 items |
| `aws_whats_new_rss.xml` | https://aws.amazon.com/about-aws/whats-new/recent/feed/ | 17 hand-picked items (AI, non-AI, "agent" false positives); descriptions cut to 300 chars |
| `huggingface_daily_papers.json` | https://huggingface.co/api/daily_papers | 14 of 50 papers (the 12 most upvoted + 2 with ≤ 1 vote), API order kept; abstracts cut to 300 chars; authors, submitters, organizations and media removed |
| `article_anthropic.html` | https://www.anthropic.com/news/accenture-embedded-evaluation | `<head>` meta tags only |
| `article_deepmind.html` | https://deepmind.google/blog/introducing-gemini-38-live-with-live-avatar/ | `<head>` meta tags only |
| `robots_aws.txt` | https://aws.amazon.com/robots.txt | none (uses wildcard rules) |

Tests never touch the network: `tests/conftest.py` blocks sockets for the whole session.

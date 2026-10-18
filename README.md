# Extriver Onboarding

Research and onboarding lead lists for creator partnerships.

## Influencer leads
- `data/extriver_influencer_leads.xlsx`: accumulated spreadsheet of publicly sourced creators from Canada, Singapore and Brazil.
- `data/extriver_influencer_leads.csv`: Excel-compatible editable mirror, intended for deduplication and hourly append workflows.
- `data/INFLUENCER_EMAIL_OUTREACH_GUIDE.md`: detailed influencer email outreach playbook (segmentation, verified contact sourcing, HTML email templates, deduplication, send/follow-up rules, campaign reporting).

Each batch targets 10 finance/investing + 10 career/admissions creators (20 total), with public business email, Instagram/YouTube/TikTok profiles, individual platform counts, references, dates and an outreach status. Empty cells mean the data could not be independently verified. Never invent email addresses, never send outreach as part of sourcing, and deduplicate by normalized social profile URL or handle before each append.

Initial batch: 2026-10-17 (Canada 8 / Singapore 6 / Brazil 6; 20 leads total, 7 publicly listed business emails).

## Korea: hourly discovery (new workflow)
- CSV: [data/korean_influencer_leads.csv](data/korean_influencer_leads.csv) (separate from the international dataset).
- Runner: [.github/workflows/discover-korean-influencers.yml](.github/workflows/discover-korean-influencers.yml).
- Script: [scripts/discover_korean_influencers.py](scripts/discover_korean_influencers.py).
- GitHub Actions triggers once an hour at minute 17 **UTC**, plus optional manual **Run workflow**.
- Each run searches Korean-language creator categories including finance/investing, careers, admissions/education, beauty/fashion, technology, gaming, travel/food, fitness and parenting/lifestyle.
- **Maximum 30 new rows per run, not a 30-row guarantee.** Include a lead only when a publicly displayed email appears on a creator profile, a social-linked site, or the search-result snippet. Snippet-only emails are marked *recheck recommended*, not independently confirmed by page retrieval.
- Captures category, channel/profile URL, business email, evidence/source URL, search query and UTC discovery time. Deduplicates against *both* CSV files using email or profile URL. Never fabricates an address; missing verified contacts reduce the number of records.
- Uses the \`ddgs\` metasearch backend without any required API key. Search services may rate-limit, block bots, or return sparse results. For improved search reliability, optionally set GitHub Actions repository secret \`SERPER_API_KEY\` with your own Serper.dev key. API usage may incur external charges.
- GitHub Actions must be **enabled**, and Settings → Actions → General → Workflow permissions must permit the workflow's \`GITHUB_TOKEN\` to write repository contents (or an authorized owner must change it).
- This workflow only **collects public business contacts**. It does **not** send emails or DMs.

To test immediately: GitHub → Actions → **Discover Korean influencers hourly** → **Run workflow**; view the log's summary and any new CSV commit.

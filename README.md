# Green Weekly dashboard (free, automatic)

Every Monday, GitHub runs `build_dashboard.py`, which pulls the last 7 days of
headlines from Google News RSS (one search per topic) plus a few trusted feeds,
builds a web page, and publishes it on GitHub Pages. No computer of yours needs to be on.

## Setup (about 10 minutes)

1. Create a free account at github.com, then click **New repository**.
   Name it e.g. `green-weekly`, set it to **Public**, and create it.
2. Upload every file from this folder to the repo, keeping the structure
   (`.github/workflows/weekly.yml` must stay in that exact path).
   Easiest way: on the repo page choose **Add file > Upload files** and drag the
   unzipped folder contents in. If the hidden `.github` folder doesn't upload,
   use **Add file > Create new file**, type `.github/workflows/weekly.yml` as the
   name, and paste the file's contents.
3. Go to **Settings > Pages**. Under **Build and deployment > Source**, choose **GitHub Actions**.
4. Go to the **Actions** tab, open **Weekly green dashboard**, click **Run workflow**.
   (If asked, enable workflows first.)
5. After about a minute the run turns green. Your dashboard is at
   `https://<your-username>.github.io/green-weekly/` (also shown in the run summary).

From then on it rebuilds every Monday 00:00 UTC (07:00 WIB).

## Customize

Edit `feeds.json` on GitHub (pencil icon):
- `topics`: change names and search queries. Google search operators work (`OR`, quotes).
- `trusted_feeds`: add any site's RSS URL.
- `days` and `max_per_topic`: time window and items per topic.
- `language`: for Indonesian results use `{"hl": "id", "gl": "ID", "ceid": "ID:id"}`.
  For both languages, duplicate a topic with an Indonesian query.
- Schedule: edit the `cron` line in `.github/workflows/weekly.yml`.

## Good to know

- GitHub pauses scheduled runs on a repo after 60 days with no repo activity.
  If the page stops updating, open the Actions tab and re-enable it (or click Run workflow).
- A feed that fails is skipped and logged; the page still builds from the rest.
- Headlines are matched by keywords, so a few results can be off-topic. Tighten the queries in `feeds.json`.
- To test on your own computer: `python build_dashboard.py`, then open `docs/index.html`.

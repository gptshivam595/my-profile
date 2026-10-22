# Glass wave

GitHub profile READMEs cannot run WebGL or JavaScript. `render_glass_wave.py` builds an animated GIF from the public contribution calendar. Bar height and color follow each day's real count. The moving light and contour lines are animation only and do not add contributions.

No token is required.

Data sources:

- `https://github.com/users/<username>/contributions` for daily counts
- `https://api.github.com/users/<username>` for the name, join date, and public repository count

Window: the last 52 weeks, labeled on the image.

Cards, all for that same window unless noted:

- Total contributions: sum of daily counts
- Longest streak: most consecutive days with at least one contribution
- Active since: account creation date
- Repositories: public repositories only

Refresh from Actions → Glass Wave → Run workflow. It also runs every day.

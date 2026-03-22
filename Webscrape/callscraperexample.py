from Forecast.Webscrape.quick_scrape import scrape_url

results = scrape_url(
    "https://homelesshub.ca/community-profiles/waterloo-region",
    "people experiencing homelessness",
    "chronic homelessness",
    "unemployment rate",
    "appartment vacancy rate",
    "average cost of rent (1 bdrm)",
)

print(results)
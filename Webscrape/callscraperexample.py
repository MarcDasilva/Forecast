from Forecast.Webscrape.quick_scrape import scrape_url

results = scrape_url(
    "https://www.er-watch.ca/",
    "WRHN Midtown"
)

print(results)
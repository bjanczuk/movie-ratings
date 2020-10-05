from movie import Movie

import collections
import enchant
import html
import json
import matplotlib.pyplot as plt
import numpy as np
import os
import re
import requests
import statistics

HEADERS = { 'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.87 Safari/537.36' }

UTF8 = "utf-8"
CACHE_FILEPATH = "./cache/cache.txt"
IMDB_CACHE_FILEPATH = "./cache/IMDB_cache.txt"
RT_CACHE_FILEPATH = "./cache/RT_cache.txt"

ERROR_INDENT = "\t" * 4

CUTOFF_YEAR = 1950
RT_MOVIES_PER_YEAR_LIMIT = 50

IMDB_REGEX_TOP_1000 = """<a href="(\/title\/.*?)\/.*[\n\r\s]+>(.*?)<\/a>[\n\r\s]+<span class="lister-item-year text-muted unbold">\((.*?)\)<\/span>[\n\r\s]+<\/span>[\n\r\s]+<\/span>[\n\r\s]+<\/div>[\n\r\s]+<div class="col-imdb-rating">[\n\r\s]+<strong title="(.*?) base on (.*?) votes">"""
IMDB_REGEX_QUERY_RESULTS = """<td class="result_text"> <a href="(.*?)\?ref_.*?" >(.*?)<\/a> \(([0-9]+)\).*?<\/td> <\/tr>"""
IMDB_REGEX_MOVIE_PAGE_RATING = """<strong title="(.*?) based on (.*?) user ratings">"""
IMDB_REGEX_MOVIE_PAGE_GENRE = """\/search\/title\?genres=([a-z]+)"""
RT_REGEX_TOP_EACH_YEAR = """&nbsp;([0-9]+)%<\/span>[\n\r\s]+<\/span>[\n\r\s]+<\/td>[\n\r\s]+<td>[\n\r\s]+.*class="unstyled articleLink">[\n\r\s]+(.*?)\([0-9]+\)<\/a>[\n\r\s]+<\/td>[\n\r\s]+.*?([0-9]+)"""
RT_REGEX_QUERY_RESULTS = """<script id="movies-json" type="application\/json">(.*?})<\/script>"""
RT_REGEX_MOVIE_PAGE_REVIEWS = """"reviewCount":([0-9]+)"""

GENRE_CUTOFF_AMOUNT = 20

def loadCache():
	moviesDict = dict()
	moviesSet = set()

	if os.path.exists(CACHE_FILEPATH):
		with open(CACHE_FILEPATH, encoding=UTF8) as file:
			cacheMovies = file.readlines()
			for movieLine in cacheMovies:
				m = Movie()
				m.loadFromCache(movieLine)
				moviesSet.add(m)
				moviesDict[m.getDictKey()] = m

	return (moviesDict, moviesSet)

def saveToCache(moviesSet, filePath=CACHE_FILEPATH):
	with open(filePath, "w", encoding=UTF8) as file:
		for m in moviesSet:
			file.write(m.getCacheJson())

def getRequest(url):
	try:
		r = requests.get(url, headers=HEADERS)
		return r.text
	except Exception as e:
		print("Exception while making GET request for {}: {}".format(url, e))
		return ''

def scrapeTop1000IMDB(moviesDict, moviesSet):
	print("Starting scraping of IMDB top 100...")
	step = 250

	for i in range(1, 1000, step):
		filePath = "./cache/requests/imdb_top1000_{}".format(i)
		if os.path.exists(filePath):
			with open(filePath, encoding=UTF8) as file:
				requestHTML = file.read()
		else:
			if i == 1:
				url = "https://www.imdb.com/search/title/?groups=top_1000&sort=user_rating,desc&count={}&view=simple".format(step)
			else:
				url = "https://www.imdb.com/search/title/?groups=top_1000&view=simple&sort=user_rating,desc&count={}&start={}".format(step, i)

			requestHTML = getRequest(url)

			with open(filePath, "w", encoding=UTF8) as file:
				file.write(requestHTML)

		for match in re.findall(IMDB_REGEX_TOP_1000, requestHTML):
			movieUrl, title, year, rating, votes = match
			title = normalizeTitle(title)
			m = Movie(title, int(''.join([c for c in year if c.isdigit()])))
			m.IMDBrating = float(rating)
			m.IMDBvotes = int(votes.replace(',', ''))

			if m.year >= CUTOFF_YEAR and m not in moviesSet:
				moviePageHtml = getRequest("https://imdb.com" + movieUrl.strip())
				m.genres = set(getIMDBGenres(moviePageHtml))

				moviesSet.add(m)
				moviesDict[m.getDictKey()] = m

	saveToCache(moviesSet)
	print("...finished scraping IMDB top 100.")

def scrapeTopRTByYear(moviesDict, moviesSet):
	print("Starting scraping of Rotten Tomatoes top movies by year...")

	for year in range(2019, CUTOFF_YEAR - 1, -1):
		filePath = "./cache/requests/rt_top_{}".format(year)
		if os.path.exists(filePath):
			with open(filePath, encoding=UTF8) as file:
				requestHTML = file.read()
		else:
			url = "https://www.rottentomatoes.com/top/bestofrt/?year={}".format(year)

			requestHTML = getRequest(url)

			with open(filePath, "w", encoding=UTF8) as file:
				file.write(requestHTML)

		for counter, match in enumerate(re.findall(RT_REGEX_TOP_EACH_YEAR, requestHTML)):
			if counter == RT_MOVIES_PER_YEAR_LIMIT:
				break

			rating, title, reviews = match
			title = normalizeTitle(title)
			m = Movie(title, year)

			found = m in moviesSet
			if not found:
				if Movie(title, year + 1) in moviesSet:
					m.year += 1
					found = True
				elif Movie(title, year - 1) in moviesSet:
					m.year -= 1
					found = True
			
			if not found:
				moviesSet.add(m)
				moviesDict[m.getDictKey()] = m

			moviesDict[m.getDictKey()].RTrating = int(rating)
			moviesDict[m.getDictKey()].RTreviews = int(reviews)

	saveToCache(moviesSet)
	print("...finished scraping Rotten Tomatoes top movies by year.")

def queryIMDBForMissing(moviesDict, moviesSet):
	print("Starting querying and scraping for missing IMDB movies...")
	missingMovies = {m for m in moviesSet if m.IMDBrating == 0}
	successfulCount, unsuccessfulCount = 0, 0

	# Run an IMDB search using every missing movie title.
	for m in missingMovies:
		url = "https://www.imdb.com/find?q={}&s=tt&ref_=fn_al_tt_mr".format(m.title.lower())
		requestHTML = getRequest(url)
		try:
			startIndex = requestHTML.index("<td class=\"result_text\">")
			requestHTML = requestHTML[startIndex:startIndex+5000].replace(' (I)', '')
		except ValueError:
			print(ERROR_INDENT + "IMDB search failure (exception): {} ({})".format(m.title, m.year))
			continue

		# Loop over the results and look for a movie that has a matching title and year.
		success = False
		for match in re.findall(IMDB_REGEX_QUERY_RESULTS, requestHTML):
			movieUrl, title, year = match
			title = normalizeTitle(title)
			year = int(year)
			
			if (titlesAndYearsMatch(m.title, title, m.year, year)):
				requestHTML = getRequest("https://www.imdb.com" + movieUrl.strip())

				ratingMatch = re.search(IMDB_REGEX_MOVIE_PAGE_RATING, requestHTML)
				if ratingMatch != None:
					success = True
					successfulCount += 1
					moviesDict[m.getDictKey()].IMDBrating = float(ratingMatch.groups()[0])
					moviesDict[m.getDictKey()].IMDBvotes = int(ratingMatch.groups()[1].replace(',', ''))
					moviesDict[m.getDictKey()].genres = set(getIMDBGenres(requestHTML))

					moviesSet.remove(m)
					moviesSet.add(moviesDict[m.getDictKey()])
					saveToCache(moviesSet)
					print("IMDB search success: {} ({}) ({})".format(m.title, m.year, moviesDict[m.getDictKey()].genres))
					break

		if not success:
			unsuccessfulCount += 1
			print(ERROR_INDENT + "IMDB search failure: {} ({})".format(m.title, m.year))

	print("...finished querying and scraping for missing IMDB movies.")

def queryRTForMissing(moviesDict, moviesSet):
	print("Starting querying and scraping for missing Rotten Tomatoes movies...")

	missingMovies = {m for m in moviesSet if m.RTrating == 0}
	successfulCount, unsuccessfulCount = 0, 0

	# Run a Rotten Tomatoes search using every missing movie title.
	for m in missingMovies:
		url = "https://www.rottentomatoes.com/search?search={}".format(m.title.lower())
		requestHTML = getRequest(url)
		jsonMatch = re.search(RT_REGEX_QUERY_RESULTS, requestHTML)

		if jsonMatch == None:
			print(ERROR_INDENT + "Error searching Rotten Tomatoes for: {}".format(m.title))
			continue

		jsonDict = json.loads(jsonMatch.group(1))

		# Loop over the results and look for a movie that has a matching title and year.
		success = False
		for movieObject in jsonDict["items"]:
			if "score" in movieObject["tomatometerScore"]:
				title = movieObject["name"]
				title = normalizeTitle(title)
				year = int(movieObject["releaseYear"])

				if (titlesAndYearsMatch(m.title, title, m.year, year)):
					requestHTML = getRequest(movieObject["url"])
					match = re.search(RT_REGEX_MOVIE_PAGE_REVIEWS, requestHTML)
					
					if match != None:
						success = True
						successfulCount += 1
						moviesDict[m.getDictKey()].RTrating = int(movieObject["tomatometerScore"]["score"])
						moviesDict[m.getDictKey()].RTreviews = int(match.group(1))

						moviesSet.remove(m)
						moviesSet.add(moviesDict[m.getDictKey()])
						saveToCache(moviesSet)
						print("Rotten Tomatoes search success: {} ({})".format(m.title, m.year))
						break

		if not success:
			unsuccessfulCount += 1
			print(ERROR_INDENT + "Rotten Tomatoes search failure: {} ({})".format(m.title, m.year))

	print("...finished querying and scraping for missing Rotten Tomatoes movies.")

def normalizeTitle(title):
	title = title.strip()
	title = html.unescape(title)
	title = removeTranslation(title)
	title = title.replace(" & ", " and ")
	title = title.strip("?!\"',.")
	return title.strip()

def getIMDBGenres(html):
	genres = set()

	for genreMatch in re.findall(IMDB_REGEX_MOVIE_PAGE_GENRE, html)[:3]:
		genres.add(genreMatch)

	return genres

# Removes the translated version of the movie title if there is one.
def removeTranslation(title):
	match = re.search("\(.*?\)$", title)

	if match != None:
		d = enchant.Dict("en_US")

		splitPoint = title.index(match.group())
		left, right = title[:splitPoint], title[splitPoint:].strip("()")
		leftTranslatedCount = len([w for w in left.split() if not d.check(w)])
		rightTranslatedCount = len([w for w in right.split() if not d.check(w)])

		if leftTranslatedCount == 0 and rightTranslatedCount >= 1:
			title = left.strip()
		elif rightTranslatedCount == 0 and leftTranslatedCount >= 1:
			title = right.strip()

	return title

def titlesAndYearsMatch(title1, title2, year1, year2):
	tempTitle1 = [c for c in title1.lower() if c.isalpha()]
	tempTitle2 = [c for c in title2.lower() if c.isalpha()]

	titlesMatch = (tempTitle1 == tempTitle2) or (tempTitle1 in tempTitle2) or (tempTitle2 in tempTitle1)
	yearsMatch = (year2 - 1 <= year1 <= year2 + 2) or (year1 - 1 <= year2 <= year1 + 2)
	return titlesMatch and yearsMatch
	
if __name__ == '__main__':
	# Start by loading any movies that have already been scraped from the cache.
	moviesDict, moviesSet = loadCache()

	# Get the top 1000 movie names and ratings from IMDB.
	scrapeTop1000IMDB(moviesDict, moviesSet)

	# Get the top movies from Rotten Tomatoes for each year.
	scrapeTopRTByYear(moviesDict, moviesSet)

	# Query IMDB for movies that only have Rotten Tomatoes ratings so far.
	queryIMDBForMissing(moviesDict, moviesSet)

	# Query Rotten Tomatoes for movies that only have IMDB ratings so far.
	queryRTForMissing(moviesDict, moviesSet)

	imdbMoviesOnly = {m for m in moviesSet if m.IMDBrating != 0 and m.RTrating == 0}
	rtMoviesOnly = {m for m in moviesSet if m.IMDBrating == 0 and m.RTrating != 0}
	print("\nData found from both websites for {} movies.".format(len({m for m in moviesSet if m.IMDBrating != 0 and m.RTrating != 0})))
	print("Data found from IMDB only for {} movies.".format(len(imdbMoviesOnly)))
	print("Data found from Rotten Tomatoes only for {} movies.".format(len(rtMoviesOnly)))
	saveToCache(imdbMoviesOnly, IMDB_CACHE_FILEPATH)
	saveToCache(rtMoviesOnly, RT_CACHE_FILEPATH)
	print("\n\n")

	#### Now that data has been scraped, actually analyze the movie ratings. ####
	moviesSet = {m for m in moviesSet if m.IMDBrating != 0 and m.RTrating != 0}

	# Genre counts.
	genreCounts = collections.defaultdict(int)
	for movie in moviesSet:
		for genre in movie.genres:
			genreCounts[genre] += 1

	# Basic rating analysis.
	imdbRatingsCounter = collections.Counter([m.IMDBrating for m in moviesSet])
	plt.plot([k for k in sorted(imdbRatingsCounter)], [imdbRatingsCounter[k] for k in sorted(imdbRatingsCounter)])
	plt.title("IMDB Ratings Distribution")
	plt.xlabel("Rating")
	plt.ylabel('Number of Movies')
	plt.show()

	rtRatingsCounter = collections.Counter([m.RTrating for m in moviesSet])
	plt.plot([k for k in sorted(rtRatingsCounter)], [rtRatingsCounter[k] for k in sorted(rtRatingsCounter)])
	plt.title("Rotten Tomatoes Ratings Distribution")
	plt.xlabel("Rating")
	plt.ylabel('Number of Movies')
	plt.show()

	differences = list()
	genreDifferences = collections.defaultdict(list)
	for movie in moviesSet:
		diff = (movie.IMDBrating * 10) - movie.RTrating
		differences.append(diff)
		for genre in movie.genres:
			genreDifferences[genre].append(diff)

	differencesCounter = collections.Counter(differences)
	plt.plot([k for k in sorted(differencesCounter)], [differencesCounter[k] for k in sorted(differencesCounter)])
	plt.title("IMDB vs. RT: Rating Differences")
	plt.xlabel("Difference between IMDB and RT Rating")
	plt.ylabel('Number of Movies')
	plt.show()


	imdbGenreRatings = collections.defaultdict(list)
	rtGenreRatings = collections.defaultdict(list)
	imdbYearRatings = collections.defaultdict(list)
	rtYearRatings = collections.defaultdict(list)

	for movie in moviesSet:
		for genre in movie.genres:
			imdbGenreRatings[genre].append(movie.IMDBrating * 10)
			rtGenreRatings[genre].append(movie.RTrating)

		imdbYearRatings[movie.year].append(movie.IMDBrating * 10)
		rtYearRatings[movie.year].append(movie.RTrating)

	# Plot average rating for both IMDB and RT by genre.
	genres = sorted([k for k in genreCounts if genreCounts[k] >= GENRE_CUTOFF_AMOUNT])
	imdbGenreAvgs = [statistics.mean(imdbGenreRatings[genre]) for genre in genres]
	rtGenreAvgs = [statistics.mean(rtGenreRatings[genre]) for genre in genres]

	ax = plt.subplot(111)
	w = 0.3
	_x = np.arange(len(genres))
	ax.bar(_x - (w / 2), imdbGenreAvgs, width=w, color='yellow', align='center')
	ax.bar(_x + (w / 2), rtGenreAvgs, width=w, color='r', align='center')
	plt.xticks(_x, genres)
	ax.set_xticklabels(genres, rotation=45)
	plt.title("Average Rating By Genre")
	plt.ylabel('Average Rating')
	plt.show()

	# Plot the average difference (IMDB rating - RT rating) for each genre.
	genres = [k for k in sorted(genreDifferences, key=lambda x: statistics.mean(genreDifferences[x]), reverse=True) if genreCounts[k] >= GENRE_CUTOFF_AMOUNT]
	ax = plt.subplot(111)
	_x = np.arange(len(genres))
	ax.bar(_x, [statistics.mean(genreDifferences[genre]) for genre in genres], color='orange', align='center')
	plt.xticks(_x, genres)
	ax.set_xticklabels(genres, rotation=45)
	plt.title("IMDB vs. RT: Average Difference In Rating By Genre")
	plt.ylabel('Average Difference')
	plt.show()

	# Plot average rating for both IMDB and RT by year of movie release.
	years = sorted(imdbYearRatings.keys())
	imdbYearAvgs = [statistics.mean(imdbYearRatings[year]) for year in years]
	rtYearAvgs = [statistics.mean(rtYearRatings[year]) for year in years]
	yearAvgs = [statistics.mean(zipped) for zipped in zip(imdbYearAvgs, rtYearAvgs)]

	ax = plt.subplot(111)
	w = 0.2
	_x = np.arange(len(years))
	ax.bar(_x - (w / 2), imdbYearAvgs, width=w, color='yellow', align='center')
	ax.bar(_x + (w / 2), rtYearAvgs, width=w, color='r', align='center')
	ax.plot(_x, yearAvgs)
	plt.xticks(_x, years)
	ax.set_xticklabels(years, rotation=80)
	plt.title("IMDB vs. RT: Average Rating By Year")
	plt.ylabel('Average Rating')
	plt.show()
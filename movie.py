import json

class Movie:
	def __init__(self, title='', year=0):
		self.title = title
		self.year = year
		self.IMDBrating = 0
		self.IMDBvotes = 0
		self.RTrating = 0
		self.RTreviews = 0
		self.genres = set()

	def __eq__(self, other):
		return self.title == other.title and self.year == other.year

	def __hash__(self):
		return hash(self.getDictKey())

	def getDictKey(self):
		return (self.title, self.year)

	def getCacheJson(self):
		movieDict = dict()
		movieDict["title"] = self.title
		movieDict["year"] = self.year
		movieDict["IMDBrating"] = self.IMDBrating
		movieDict["IMDBvotes"] = self.IMDBvotes
		movieDict["RTrating"] = self.RTrating
		movieDict["RTreviews"] = self.RTreviews
		movieDict["genres"] = list(self.genres)

		return json.dumps(movieDict) + "\n"

	def loadFromCache(self, jsonString):
		movieDict = json.loads(jsonString)
		self.title = movieDict["title"]
		self.year = movieDict["year"]
		self.IMDBrating = movieDict["IMDBrating"]
		self.IMDBvotes = movieDict["IMDBvotes"]
		self.RTrating = movieDict["RTrating"]
		self.RTreviews = movieDict["RTreviews"]
		self.genres = set(movieDict["genres"])
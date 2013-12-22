import sys
if sys.version < '2.7.3': #If crappy html.parser, use internal version. Using internal version on ATV2 crashes as of XBMC 12.2, so that's why we test version
	print 'Blu-ray.com: Using internal HTMLParser'
	import HTMLParser # @UnusedImport
	
import re, requests, bs4, urllib # @UnresolvedImport

class ResultItem:
	_resultType = 'None'
	_hr = '[COLOR FF606060]%s[/COLOR]' % ('_' * 200)
	
	def __init__(self,soupData):
		self.title = ''
		self.icon = ''
		self.ID = ''
		self.processSoupData(soupData)
	
	def __str__(self):
		return '<%s=%s %s>' % (self._resultType,self.title,self.ID)
	
	def processSoupData(self,soupData):
		pass
	
	def convertTable(self,soup,table,sep=' '):
		if not table: return
		text = '[CR]'
		for td in table.findAll('tr'):
			text += td.getText(separator=sep) + '[CR]'
		tag = soup.new_tag('p')
		tag.string = text
		table.replaceWith(tag)
		
	def convertUL(self,soup,ul):
		text = '[CR]'
		for li in ul.findAll('li'):
			text += li.getText() + '[CR]%s[CR]' % self._hr
		tag = soup.new_tag('p')
		tag.string = text
		ul.replaceWith(tag)
	
class ReviewsResult(ResultItem):
	_resultType = 'ReviewsResult'
	
	def __init__(self,soupData):
		self.description = ''
		self.rating = ''
		self.ratingImage = ''
		self.info = ''
		self.url = ''
		self.genre = ''
		self.flagImage = ''
		ResultItem.__init__(self, soupData)
		
	def processSoupData(self,soupData):
		self.title = soupData.find('h3').getText().strip()
		flagImg = soupData.find('img',{'src':lambda x: 'flag' in x})
		if flagImg: self.flagImage = flagImg.get('src','')
		images = soupData.findAll('img')
		self.icon = images[0].get('src')
		self.rating = images[-1].get('alt')
		self.ratingImage = images[-1].get('src')
		data = soupData.findAll('p',text=True)
		try:
			self.info = data[-3].text
		except:
			print 'INFO ERROR'
		try:
			self.description = data[-2].text
		except:
			print 'NO DESCRIPTION'
		self.genre = data[-1].text
		self.url = soupData.find('a').get('href')
		self.ID = self.url.strip('/').rsplit('/')[-1]

class ReviewsResultJSON(ReviewsResult):
	def processSoupData(self,json):
		self.title = json.get('title','')
		self.url = json.get('url','')
		self.icon = json.get('cover','')
		self.flagImage = json.get('flag','')
		rating = json.get('rating','')
		self.ratingImage = 'http://www.blu-ray.com/images/rating/b%s.jpg' % (rating or '0')
		self.info = json.get('year','') + ' | ' + json.get('reldate','')
		try:
			self.rating = 'Overall: %.1f of 5' % (int(rating)/2.0)
		except:
			pass
		
class Review(ReviewsResult):
	_resultType = 'Review'
	def __init__(self,soupData):
		self.flagImage = ''
		self.coverImage = ''
		self.images = []
		self.review = ''
		self.overview = ''
		self.specifications = ''
		self.historyGraphs = []
		self.otherEditions = []
		self.similarTitles = []
		ReviewsResult.__init__(self, soupData)
		
	def processSoupData(self,soupData):
		flagImg = soupData.find('img',{'src':lambda x: 'flags' in x})
		if flagImg: self.flagImage = flagImg.get('src','')
		
		for h3 in soupData.findAll('h3'):
			for i in h3.findAll('img'):
				tag = soupData.new_tag('p')
				tag.string = i.get('alt','')
				i.replaceWith(tag)
			h3r = soupData.new_tag('p')
			h3r.string = '[CR][COLOR FF0080D0][B]%s[/B][/COLOR][CR]' % h3.getText()
			h3.replaceWith(h3r)
			
		for i in soupData.findAll('img',{'id':'reviewScreenShot'}):
			src = i.get('src','')
			p1080 = src.replace('.jpg','_1080p.jpg')
			self.images.append((src,p1080))
			idx = src.rsplit('.',1)[0].split('_',1)[-1]
			tag = soupData.new_tag('p')
			tag.string = '[CR][COLOR FFA00000]IMAGE %s[/COLOR][CR]' % idx
			i.replaceWith(tag)
		self.title = soupData.find('title').getText(strip=True)
		
		coverImg = soupData.find('img',{'id':'frontimage_overlay'})
		if coverImg: self.coverImage = coverImg.get('src','')
		
		reviewSoup = soupData.find('div',{'id':'reviewItemContent'})
		
		if reviewSoup:
			self.convertTable(soupData, reviewSoup.find('table'))
			self.review = reviewSoup.getText(strip=True)
			
		if self.review.startswith('[CR]'): self.review = self.review[4:]
		sections = soupData.findAll('div',{'data-role':'collapsible'})
		
		self.convertTable(soupData, sections[0].find('table'),sep=': ')
		self.overview = sections[0].getText()
		
		self.convertUL(soupData,sections[1].find('ul'))
		self.specifications = sections[1].getText()
		if not len(sections) > 3: return
		for i in sections[3].findAll('img'):
			source = i.previous_sibling
			source = source and ('[COLOR ' + source.string.rsplit('[COLOR ',1)[-1]) or '?'
			source = re.sub('\[[^\]]+?\]','',source)
			self.historyGraphs.append((source,i.get('src','')))
		
		if not len(sections) > 4: return
		for li in sections[4].findAll('li'):
			self.otherEditions.append((li.find('a').get('href'),li.find('img').get('src'),removeColorTags(li.getText())))
		
		if not len(sections) > 5: return
		for li in sections[5].findAll('li'):
			self.similarTitles.append((li.find('a').get('href'),li.find('img').get('src'),removeColorTags(li.getText())))
		
def removeColorTags(text):
	return re.sub('\[/?COLOR[^\]]*?\]','',text)
	
class BlurayComAPI:
	reviewsURL = 'http://m.blu-ray.com/movies/reviews.php'
	releasesURL = 'http://m.blu-ray.com/movies'
	searchURL = 'http://m.blu-ray.com/quicksearch/search.php?country=ALL&section=bluraymovies&keyword={0}'
	pageARG = 'page=%s'
	
	def __init__(self):
		pass
	
	def url2Soup(self,url):
		req = requests.get(url)
		return bs4.BeautifulSoup(req.text)
	
	def getCategories(self):
		return [('Reviews','','reviews'),('Releases','','releases'),('Search','','search')]
	
	def getReleases(self):
		items = []
		soup = self.url2Soup(self.releasesURL)
		for i in soup.findAll('li',{'data-role':lambda x: not x}):
			items.append(ReviewsResult(i))
		return items
	
	def getReviews(self,page=''):
		if page: page = '?' + self.pageARG % page
		soup = self.url2Soup(self.reviewsURL + page)
		items = []
		for i in soup.findAll('li',{'data-role':lambda x: not x}):
			items.append(ReviewsResult(i))
		return items
	
	def getReview(self,url):
		req = requests.get(url)
		
		fixed = ''
		for line in req.text.splitlines():
			new = line.rstrip()
			if new != line: new += ' '
			line = new.lstrip()
			if line != new: line = ' ' + line
			fixed += line 
		fixed = re.sub('<i>(?i)','[I]',fixed)
		fixed = re.sub('</i>(?i)',' [/I]',fixed)
		fixed = re.sub('<br[^>]*?>(?i)','[CR]',fixed)
		soup = bs4.BeautifulSoup(fixed,from_encoding=req.encoding)
		return Review(soup)
	
	def search(self,terms):
		req = requests.get(self.searchURL.format(urllib.quote(terms)))
		results = []
		for i in req.json().get('items',[]):
			results.append(ReviewsResultJSON(i))
		return results
		
		

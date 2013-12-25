import sys, hashlib, time
if sys.version < '2.7.3': #If crappy html.parser, use internal version. Using internal version on ATV2 crashes as of XBMC 12.2, so that's why we test version
	print 'Blu-ray.com: Using internal HTMLParser'
	import HTMLParser # @UnusedImport
import html5lib # @UnusedImport
import re, requests, bs4, urllib # @UnresolvedImport

def LOG(msg):
	print msg
	
TR = {	'reviews':'Reviews',
		'releases':'Releases',
		'deals':'Deals',
		'search':'Search',
		'collection':'Collection',
		'watched':'Watched',
		'yes':'Yes'
}

def minsToDuration(mins):
	try:
		mins = int(mins)
	except:
		return str(mins)
	hrs = mins/60
	mins = mins%60
	hrsd = hrs > 1 and 'hrs' or 'hr'
	minsd = mins > 1 and 'mins' or 'min'
	return '%d %s %d %s' % (hrs,hrsd,mins,minsd)
	
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
		
	def convertHeaders(self,soup,tag):
		for h3 in tag.findAll('h3'):
			for i in h3.findAll('img'):
				tag = soup.new_tag('p')
				tag.string = i.get('alt','')
				i.replaceWith(tag)
			h3r = soup.new_tag('p')
			h3r.string = '[CR][COLOR FF0080D0][B]%s[/B][/COLOR][CR]' % h3.getText(strip=True)
			h3.replaceWith(h3r)
			
	def cleanWhitespace(self,text):
		return re.sub('\[CR\]\s+','[CR]',text).strip()
			
class ReviewsResult(ResultItem):
	_resultType = 'ReviewsResult'
	
	def __init__(self,soupData):
		self._section = None
		self.description = ''
		self.rating = ''
		self.ratingImage = ''
		self.info = ''
		self.url = ''
		self.genre = ''
		self.flagImage = ''
		self.previous = None
		self.next = None
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
			LOG('INFO ERROR')
		try:
			self.description = data[-2].text
		except:
			LOG('NO DESCRIPTION')
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
		
class ReleasesResult(ReviewsResult):
	def processSoupData(self,soupData):
		self.title = soupData.find('h3').getText().strip()
		images = soupData.findAll('img')
		self.icon = images[0].get('src')
		data = soupData.findAll('p',text=True)
		try:
			self.info = data[-3].text #Will probably never give anything
		except:
			pass
		try:
			self.description = data[-2].text
		except:
			pass
		self.info = data[-1].text
		self.url = soupData.find('a').get('href')
		self.ID = self.url.strip('/').rsplit('/')[-1]
		
class DealsResult(ReviewsResult):
	def processSoupData(self,soupData):
		self.title = soupData.find('h3').getText().strip()
		price = []
		for span in soupData.find('span').findAll('span'):
			color = span.get('style','').split('#',1)[-1].split(';',1)[0].upper()
			price.append((span.getText(strip=True),color))
		if len(price) > 2:
			self.description = '%s (%s)  [COLOR FF%s]%s[/COLOR]' % (price[1][0],price[2][0],price[0][1],price[0][0].upper())
		else:
			for p in price: self.description =+ p[0] + '  '
		
		images = soupData.findAll('img')
		self.icon = images[0].get('src')
			
		self.url = soupData.find('a').get('href')
		self.ID = self.url.strip('/').rsplit('/')[-1]

class CollectionResult(ReviewsResult):
	infoTags = ('runtime','studio','year','releasetimestamp')
	def __init__(self,soupData,categoryid):
		self.categoryid = categoryid
		self.sortTitle = ''
		self.json = {}
		ReviewsResult.__init__(self, soupData)
		
	'''
	rating: 8.6842
	dtadded: 1387809844
	year: 1993
	pid: 59530
	gpid: 159245
	gtin: 00025192180279
	coverurl0: http://images2.static-bluray.com/movies/covers/59530_medium.jpg
	watched: 1
	releasetimestamp: 1366689600
	ctid: 1
	countrycode: US
	title: Jurassic Park 3D
	titlesort: Jurassic Park 3D
	3d: 1
	studio: Universal Studios
	vidresid: 278
	genreids: 1,2,21
	movieid: 20587
	url: http://www.blu-ray.com/movies/Jurassic-Park-3D-Blu-ray/59530/
	studioid: 8
	runtime: 127
	casingid: 2423
	dtwatched: 1387165468
	price: 500
	pricecomment: Bin
	the: The
	edition: Extended Edition
	exclude: 1
	'''
	def processSoupData(self,json):
		json['categoryid'] = self.categoryid
		self.json = json
		self.title = json.get('title')
		the = json.get('the')
		if the: self.title = the + ' ' + self.title
		self.icon = json.get('coverurl0')
		self.url = json.get('url').replace('www','m')
		rating = json.get('rating')
		self.sortTitle = json.get('titlesort',self.title) 
		try:
			self.ratingImage = 'http://www.blu-ray.com/images/rating/b%s.jpg' % (int(float(rating)) or '0')
		except:
			pass
		self.info = json.get('year','') + ' | ' + json.get('reldate','')
		try:
			self.rating = 'Overall: %.1f of 5' % (round(round(float(rating)/2,1)*2)/2)
		except:
			pass
		self.info = ''
		infos = []
		for tag in self.infoTags:
			data = json.get(tag)
			if not data: continue
			if tag == 'runtime':
				data = minsToDuration(data)
			elif tag == 'releasetimestamp':
				try:
					data = int(data)
				except:
					continue
				data = time.strftime('%b %d, %Y',time.gmtime(data))
			infos.append(data)
		self.info = ' | '.join(infos)
		try:
			watched = int(json.get('dtwatched'))
			self.description = ('%s: ' % TR['watched']) + time.strftime('%b %d, %Y',time.localtime(watched))
		except (TypeError, ValueError):
			self.description = json.get('watched') and ('%s: %s' % (TR['watched'], TR['yes'])) or ''
		self.description += '[CR]' + json.get('comment','')
		self.genre = ''
		
	def refresh(self):
		self.processSoupData(self.json)
		
class Review(ReviewsResult):
	_resultType = 'Review'
	def __init__(self,soupData):
		self.flagImage = ''
		self.coverImage = ''
		self.images = []
		self.review = ''
		self.overview = ''
		self.specifications = ''
		self.price = ''
		self.blurayRating = ''
		self.historyGraphs = []
		self.otherEditions = []
		self.similarTitles = []
		self.subheading1 = ''
		self.subheading2 = ''
		self.owned = False
		ReviewsResult.__init__(self, soupData)
		
	def processSoupData(self,soupData):
		flagImg = soupData.find('img',{'src':lambda x: 'flags' in x})
		if flagImg: self.flagImage = flagImg.get('src','')
		
		self.owned = bool(soupData.find('a',{'href':lambda x: '/collection.php' in x})) #TODO: Login so we can actually get this to work
		
		for i in soupData.findAll('img',{'id':'reviewScreenShot'}):
			src = i.get('src','')
			p1080 = src.replace('.jpg','_1080p.jpg')
			self.images.append((src,p1080))
			idx = src.rsplit('.',1)[0].split('_',1)[-1]
			tag = soupData.new_tag('span')
			tag.string = '[CR][COLOR FFA00000]IMAGE %s[/COLOR][CR]' % idx
			i.insert_before(tag)
			
		self.title = soupData.find('title').getText(strip=True)
		
		subheadings = soupData.findAll('span',{'class':'subheading'})
		if subheadings:
			self.subheading1 = subheadings[0].getText().strip()
			if len(subheadings) > 1: self.subheading2 = subheadings[1].getText().strip()
		
		coverImg = soupData.find('img',{'id':'frontimage_overlay'})
		if coverImg: self.coverImage = coverImg.get('src','')
		
		for p in soupData.findAll('p'):
			p.replaceWith(p.getText() + '[CR]')
		reviewSoup = soupData.find('div',{'id':'reviewItemContent'})
		
		if reviewSoup:
			self.convertHeaders(soupData, reviewSoup)
			self.convertTable(soupData, reviewSoup.find('table'))
			self.review = self.cleanWhitespace(reviewSoup.getText())
			
		price_rating = soupData.findAll('div',{'class':'content2'})
		self.convertHeaders(soupData, price_rating[0])
		self.price = self.cleanWhitespace(price_rating[0].getText())
		if len(price_rating) > 1:
			self.convertHeaders(soupData, price_rating[1])
			self.convertTable(soupData, price_rating[1].find('table'))
			self.blurayRating = self.cleanWhitespace(price_rating[1].getText())
			
		sections = soupData.findAll('div',{'data-role':'collapsible'})
		for section in sections:
			h3 = section.find('h3')
			sectionName = h3 and h3.string.lower() or ''
			if 'overview' in sectionName:
				self.processOverview(soupData, section)
			elif 'specifications' in sectionName:
				self.processSpecifications(soupData, section)
			elif 'history' in sectionName:
				self.processHistoryGraphs(soupData, section)
			elif 'editions' in sectionName:
				self.processOtherEditions(soupData, section)
			elif 'similar' in sectionName:
				self.processSimilarTitles(soupData, section)
			elif 'review' in sectionName and not self.review:
				self.convertHeaders(soupData, section)
				self.review = section.getText()
				
		if self.review.startswith('[CR]'): self.review = self.review[4:]
		if self.overview.startswith('[CR]'): self.overview = self.overview[4:]
			
	def processOverview(self,soupData,section):
		self.convertHeaders(soupData, section)
		self.convertTable(soupData, section.find('table'),sep=': ')
		self.overview = self.cleanWhitespace(section.getText())
		
	def processSpecifications(self,soupData,section):
		self.convertHeaders(soupData, section)
		self.convertUL(soupData,section.find('ul'))
		self.specifications = self.cleanWhitespace(section.getText())
		
	def processHistoryGraphs(self,soupData,section):
		for i in section.findAll('img'):
			source = i.previous_sibling
			source = source and ('[COLOR ' + source.string.rsplit('[COLOR ',1)[-1]) or '?'
			source = re.sub('\[[^\]]+?\]','',source)
			self.historyGraphs.append((source,i.get('src','')))
		
	def processOtherEditions(self,soupData,section):
		self.convertHeaders(soupData, section)
		for li in section.findAll('li'):
			self.otherEditions.append((li.find('a').get('href'),li.find('img').get('src'),removeColorTags(li.getText())))
			
	def processSimilarTitles(self,soupData,section):
		self.convertHeaders(soupData, section)
		for li in section.findAll('li'):
			self.similarTitles.append((li.find('a').get('href'),li.find('img').get('src'),removeColorTags(li.getText())))
		
def removeColorTags(text):
	return re.sub('\[/?COLOR[^\]]*?\]','',text)
	
class BlurayComAPI:
	reviewsURL = 'http://m.blu-ray.com/movies/reviews.php'
	releasesURL = 'http://m.blu-ray.com/movies'
	dealsURL = 'http://m.blu-ray.com/deals/index.php'
	searchURL = 'http://m.blu-ray.com/quicksearch/search.php?country=ALL&section=bluraymovies&keyword={0}'
	siteLoginURL = 'http://forum.blu-ray.com/login.php'
	apiLoginURL = 'http://m.blu-ray.com/api/userauth.php'
	collectionURL = 'http://m.blu-ray.com/api/collection.json.php?categoryid={category}&imgsz=1&session={session_id}'
	updateCollectableURL = 'http://m.blu-ray.com/api/updatecollectable.php'
	pageARG = 'page=%s'
	
	def __init__(self):
		self.parser = None
		self.sessionID = ''
		self.user = ''
		self.password = ''
		self._session = None
	
	def session(self):
		if self._session: return self._session
		self._session = requests.session()
		self.siteLogin()
		return self._session
	
	def url2Soup(self,url):
		req = self.session().get(url)
		try:
			soup = bs4.BeautifulSoup(req.text, 'lxml')
			LOG('Using: lxml parser')
			return soup
		except:
			pass
		try:
			soup = bs4.BeautifulSoup(req.text, 'html5lib')
			LOG('Using: html5lib parser')
			return soup
		except:
			pass
		LOG('Using: html.parser parser')
		return bs4.BeautifulSoup(req.text, self.parser)
	
	def getCategories(self):
		cats = [(TR['reviews'],'','reviews'),(TR['releases'],'','releases'),(TR['deals'],'','deals'),(TR['search'],'','search')]
		if self.canLogin():
			cats.append((TR['collection'],'','collection'))
		return cats
	
	def getPaging(self,soupData):
		prevPage = None
		nextPage = None
		next_ = soupData.find('a',{'data-icon':'arrow-r'})
		prev = soupData.find('a',{'data-icon':'arrow-l'})
		if next_: nextPage = next_.get('href','').rsplit('=',1)[-1] or None
		if prev: prevPage = prev.get('href','').rsplit('=',1)[-1] or None
		return (prevPage,nextPage)
		
	def getReleases(self):
		items = []
		soup = self.url2Soup(self.releasesURL)
		section = ''
		for i in soup.findAll('li'): #,{'data-role':lambda x: not x}):
			if i.h3:
				res = ReleasesResult(i)
				if section:
					res._section = section
					section = ''
				items.append(res)
			elif i.string:
				heading = i.string.lower()
				if 'this' in heading:
					section = 'THISWEEK'
				elif 'next' in heading:
					section = 'NEXTWEEK'
		return items
	
	def getDeals(self,page=''):
		if page:
			page = '?' + self.pageARG % page
		else:
			page = ''
		items = []
		soup = self.url2Soup(self.dealsURL + page)
		for i in soup.findAll('li',{'data-role':lambda x: not x}):
			items.append(DealsResult(i))
		return (items,self.getPaging(soup))
	
	def getReviews(self,page=''):
		if page:
			page = '?' + self.pageARG % page
		else:
			page = ''
		soup = self.url2Soup(self.reviewsURL + page)
		items = []
		for i in soup.findAll('li',{'data-role':lambda x: not x}):
			items.append(ReviewsResult(i))
		return (items,self.getPaging(soup))
	
	def getReview(self,url):
		req = self.session().get(url)
		
		fixed = ''
		for line in req.text.splitlines():
			if not line.strip(): continue
			new = line.rstrip()
			#if new != line: 
			new += ' '
			line = new.lstrip()
			if line != new: line = ' ' + line
			fixed += line 
		fixed = re.sub('<i>(?i)','[I]',fixed)
		fixed = re.sub('</i>(?i)',' [/I]',fixed)
		fixed = re.sub('<br[^>]*?>(?i)','[CR]',fixed)
		soup = bs4.BeautifulSoup(fixed,self.parser,from_encoding=req.encoding)
		return Review(soup)
	
	def getCollection(self,category='7'):
		if not self.apiLogin(): return
		
		req = requests.get(self.collectionURL.format(category=category,session_id=self.sessionID))
		json = req.json()
		if not 'collection' in json:
			if not self.apiLogin(force=True): return []
			req = requests.get(self.collectionURL.format(category=category,session_id=self.sessionID))
			json = req.json()
			if not 'collection' in json: return []
		'''
		{u'collection_types': [
			{u'addcollcount': u'1', u'system': u'1', u'id': u'1', u'displayorder': u'100000', u'name': u'Owned'},
			{u'addcollcount': u'0', u'system': u'1', u'id': u'3', u'displayorder': u'100000', u'name': u'Rented'},
			{u'addcollcount': u'1', u'system': u'1', u'id': u'4', u'displayorder': u'100000', u'name': u'Ordered'},
			{u'addcollcount': u'0', u'system': u'1', u'id': u'5', u'displayorder': u'100000', u'name': u'Wishlist'},
			{u'addcollcount': u'0', u'system': u'1', u'id': u'6', u'displayorder': u'100000', u'name': u'Loaned'},
			{u'addcollcount': u'1', u'system': u'1', u'id': u'7', u'displayorder': u'100000', u'name': u'For trade'},
			{u'addcollcount': u'1', u'system': u'1', u'id': u'8', u'displayorder': u'100000', u'name': u'For sale'}]
		'''
		items = []
		for i in json['collection']:
			items.append(CollectionResult(i,category))
		items.sort(key=lambda i: i.sortTitle)
		return items
	
	def search(self,terms):
		req = requests.get(self.searchURL.format(urllib.quote(terms)))
		results = []
		for i in req.json().get('items',[]):
			results.append(ReviewsResultJSON(i))
		return results
		
	def updateCollectable(self,newdata):
		if not self.apiLogin(): return
		data = {	'session':       self.sessionID,
					'productid':     newdata.get('pid','') or '0',
					'categoryid':    newdata.get('categoryid','') or '0',
					'typeid':        newdata.get('ctid','') or '0',
					'dateadded':     newdata.get('dtadded','') or '0',
					'datewatched':   newdata.get('dtwatched','') or '0',
					'watched':       newdata.get('watched','') or '0',
					'description':   newdata.get('comment',''),
					'price':         newdata.get('price','') or '0',
					'pricecomment':  newdata.get('pricecomment',''),
					'exclude':       newdata.get('exclude','') or '0'
		}
		'''
		{u'rating': u'7.45093',
		u'vidresid': u'2181',
		u'runtime': u'112',
		u'movieid': u'33757',
		u'genreids': u'6,27',
		u'countrycode': u'US',
		u'title': u'City Slickers',
		u'releasetimestamp': u'989294400',
		u'dtadded': u'1387824662',
		u'pid': u'10866', 
		u'watched': u'1', 
		u'studioid': u'61', 
		u'gpid': u'49947', 
		u'gtin': u'00027616860958', 
		u'coverurl0': u'http://images.static-bluray.com/movies/dvdcovers/10866_medium.jpg', 
		u'year': u'1991', 
		u'url': u'http://www.blu-ray.com/dvd/City-Slickers-DVD/10866/', 
		u'studio': u'Columbia Pictures', 
		u'ctid': u'16809', 
		u'titlesort': u'City Slickers', 
		u'casingid': u'2424'}
		
		session:       1db9d4f6fba0d41ef26ebfe1f0401a49
		productid:     10866
		categoryid:    21
		typeid:        16809
		dateadded:     1387824662
		datewatched:   0
		watched:       1
		description:   
		price:         0
		pricecomment:  
		exclude:       0

		'''
		req = requests.post(self.updateCollectableURL,data=data)
		return not 'error' in req.json()
		
	def siteLogin(self,force=False):
		'''
		vb_login_username:         username
		vb_login_password:         
		s:                         
		do:                        login
		vb_login_md5password:      56b1fb1e8a1561514d1a17ae6ce0e4f9
		vb_login_md5password_utf:  56b1fb1e8a1561514d1a17ae6ce0e4f9
		'''
		if not force and self.siteLoggedOn(): return True
		if not self.canLogin(): return False
		md5Pass = hashlib.md5(self.password).hexdigest()
		self.session().post(self.siteLoginURL, {	'vb_login_username':self.user,
													'vb_login_password':'',
													's':'',
													'do':'login',
													'vb_login_md5password':md5Pass,
													'vb_login_md5password_utf':md5Pass
												})
		return self.siteLoggedOn()
		
	def siteLoggedOn(self):
		return 'bbsessionhash' in self.session().cookies
	
	def apiLogin(self,force=False):
		if not force and self.apiLoggedOn(): return True
		if not self.canLogin(): return False
		ak = 'cc32ae1a8a36f52ab0c79f030aa414fb'
		gcmregid = 'APA91bFQmwwEyckSUXeZ_oMygU77-L330OjNg3tFGbAtWQQPPmhU_w7JRJ0PFUSd1gyvkGgsrPCJVhGsrISTaMFeK9YnRlmkMGWmKcfdh7EQq2185W6MPniKxRE7Us6nSs1LrgqC2N_KJF8cMBKLtSiwjUFY5XG5Hw'
		req = requests.post(self.apiLoginURL,data={'u':self.user,'p':hashlib.md5(self.password).hexdigest(),'ak':ak,'gcmregid':gcmregid})
		json = req.json()
		if 'session' in json: self.sessionID = json['session']
		return self.apiLoggedOn()
		
	def apiLoggedOn(self):
		return bool(self.sessionID)
	
	def canLogin(self):
		return self.user and self.password
	
		

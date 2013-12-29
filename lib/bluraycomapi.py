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
		'pricetracker':'Price Track',
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
	headerColor = 'FF0080D0'
	
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
		for tr in table.findAll('tr'):
			tds = []
			for td in tr.findAll('td'):
				tdtext = td.getText(strip=True).replace('[CR]',', ')
				if tdtext: tds.append(tdtext)
			text += sep.join(tds).strip() + '[CR]'
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
		
	def convertHeaders(self,soup,tag,h='h3',no_cr=False):
		for h3 in tag.findAll(h):
			for i in h3.findAll('img'):
				tag = soup.new_tag('p')
				tag.string = i.get('alt','')
				i.replaceWith(tag)
			h3r = soup.new_tag('p')
			if no_cr:
				h3r.string = '[COLOR %s][B]%s[/B][/COLOR]' % (self.headerColor,h3.getText(strip=True))
			else:
				h3r.string = '[CR][COLOR %s][B]%s[/B][/COLOR][CR]' % (self.headerColor,h3.getText(strip=True))
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
		self.categoryID = categoryid
		self.sortTitle = ''
		self.originalURL = ''
		self.watched = False
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
		json['categoryid'] = self.categoryID
		self.json = json
		self.ID = json.get('pid')
		self.title = json.get('title')
		self.watched = json.get('watched') == '1'
		the = json.get('the')
		if the: self.title = the + ' ' + self.title
		self.icon = json.get('coverurl0')
		self.originalURL = json.get('url').replace('//ww.','//www.')
		self.url = self.originalURL
		if str(self.categoryID) in ('7','21'):
			self.url = self.originalURL.replace('www','m')
		self.sortTitle = json.get('titlesort',self.title)
		rating = json.get('rating','')
		if rating:
			try:
				self.ratingImage = 'script-bluray-com-stars_%s.png' % (int((round(float(rating) * 2)/2)*10) or '0')
			except:
				pass
			self.info = json.get('year','') + ' | ' + json.get('reldate','')
			try:
				self.rating = 'Rating: %.1f' % float(rating)
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
	
class PriceTrackingResult(ReviewsResult):
	def __init__(self,soupData):
		self.json = {}
		self.itemID = ''
		self.trackingID = ''
		self.expireUnix = 0
		self.categoryID = ''
		self.countryCode = ''
		
		self.priceMatched = False
		self.currency = '$'
		self.retailer = ''
		
		self.price = ''
		self.myPrice = ''
		self.priceRange = ''
		self.listPrice = ''
		self.originalURL = ''
		
		ReviewsResult.__init__(self, soupData)
			
	def processSoupData(self,json):
		self.json = json
		self.ID = json.get('pid','')
		self.title = json.get('title','')
		self.icon = json.get('coverurl0','').replace('_small.','_medium.')
		self.categoryID = json.get('categoryid','')
		self.originalURL = json.get('url').replace('//ww.','//www.')
		self.url = self.originalURL
		if str(self.categoryID) in ('7','21'):
			self.url = self.originalURL.replace('www','m')
		self.trackingID = json.get('gpid','')
		self.countryCode = json.get('countrycode','')
		self.itemID = json.get('id','')
		self.priceMatched = json.get('pricematch') == '1'
		self.currency = json.get('currency','$')
		self.retailer = json.get('retailer','')
		try:
			self.priceRange = int(json.get('pricerange',''))/100.0
		except:
			self.priceRange = 0
		try:
			self.price = int(json.get('price',''))/100.0
		except:
			self.price = 0
		try:
			self.myPrice = int(json.get('myprice',''))/100.0
		except:
			self.myprice = 0
		try:
			self.listPrice = int(json.get('listprice',''))/100.0
		except:
			self.listPrice
		
		myprice = '%s%.2f' % (self.currency,self.myPrice)
		price = '%s%.2f' % (self.currency,self.price)
		listprice = '%s%.2f' % (self.currency,self.listPrice)
		self.description = '%s - %s at %s (List: %s)' % (myprice,price,self.retailer,listprice)
		self.info = self.priceMatched and '[COLOR FF00AA00]Matched[/COLOR]' or ''
		try:
			self.expireUnix = int(json.get('expiretimestamp'))
		except:
			pass
		
	def refresh(self):
		self.processSoupData(self.json)

class Review(ReviewsResult):
	_resultType = 'Review'
	def __init__(self,soupData,url):
		self.flagImage = ''
		self.coverImage = ''
		self.coverFront = ''
		self.coverBack = ''
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
		self.url = url
		self.ID = self.url.strip('/').rsplit('/')[-1]
		
	def processSoupData(self,soupData):
		flagImg = soupData.find('img',{'src':lambda x: 'flags' in x})
		if flagImg: self.flagImage = flagImg.get('src','')
		
		self.owned = bool(soupData.find('a',{'href':lambda x: '/collection.php' in x}))
		
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
		if coverImg:
			self.coverImage = coverImg.get('src','')
			self.coverFront = self.coverImage.replace('_medium','_front')
			self.coverBack = self.coverImage.replace('_medium','_back')
		
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
			
class GameReview(Review):
	_resultType = 'GameReview'
	def __init__(self,soupData, reviewSoupData, url):
		self.reviewSoupData = reviewSoupData
		Review.__init__(self, soupData, url)
		
	def processSoupData(self,soupData):
		self.owned = bool(soupData.find('a',{'href':lambda x: x and ('/collection.php' in x) and ('action=showcategory' in x)}))		
		self.title = soupData.find('title').getText(strip=True)
		
		flagImg = soupData.find('img',{'src':lambda x: 'flags' in x})
		if flagImg: self.flagImage = flagImg.get('src','')
		
		subheading = soupData.find('span',{'class':'subheading'})
		if subheading: self.subheading1 = subheading.getText().strip()
		
		coverImg = soupData.find('img',{'id':'productimage'})
		if coverImg:
			self.coverImage = coverImg.get('src','')
			self.coverFront = self.coverImage.replace('_medium','_large')
			self.coverBack = ''
		
		for p in soupData.findAll('p'):
			p.replaceWith(p.getText() + '[CR]')
			
		specH3 = soupData.find('h3',text='Specifications')
		if specH3:
			for sibling in specH3.next_siblings:
				if sibling.name == 'table':
					self.convertHeaders(soupData, sibling, 'h5')
					for table in sibling.findAll('table'):
						self.convertTable(soupData, table, ': ')
					self.specifications = ('[COLOR %s][B]Specifications[/B][/COLOR][CR]' % self.headerColor) + self.cleanWhitespace(sibling.getText())
					break
			
		price_rating = soupData.find('td',{'width':'35%'})
		if price_rating:
			price = '[COLOR %s][B]Price[/B][/COLOR][CR]' % self.headerColor
			for c in price_rating.children:
				if c.name == 'h3':
					break
				elif c.name in ('br','div'):
					price += '[CR]'
				elif not c.name:
					text = c.string.strip()
					if text: price += text + ' '
				else:
					text = c.getText(strip=True)
					if text: price += text + ' '
			price = self.cleanWhitespace(price)
			while price.endswith('[CR]'): price = price[:-4]
			self.price = price
			self.getReviews()		

	def getReviews(self):
		rating = self.reviewSoupData.find('div',{'id':'ratingscore'}) or ''
		if rating:
			if rating.string == '0':
				rating = ''
			else:
				rating = 'Rating: %s[CR][CR]' % rating.string
		for tag in self.reviewSoupData.find('h3',text='Post a review').previous_siblings:
			if tag.name == 'table':
				self.convertHeaders(self.reviewSoupData, tag, 'h5',no_cr=True)
				self.review = rating + self.cleanWhitespace(tag.getText().strip())
				break
			elif 'No user reviews' in tag.string:
				self.review = rating + 'No Reviews'
				break
		del self.reviewSoupData

def removeColorTags(text):
	return re.sub('\[/?COLOR[^\]]*?\]','',text)
	
class BlurayComAPI:
	reviewsURL = 'http://m.blu-ray.com/movies/reviews.php'
	releasesURL = 'http://m.blu-ray.com/movies'
	dealsURL = 'http://m.blu-ray.com/deals/index.php'
	searchURL = 'http://m.blu-ray.com/quicksearch/search.php?country={country}&section={section}&keyword={keyword}'
	siteLoginURL = 'http://forum.blu-ray.com/login.php'
	apiLoginURL = 'http://m.blu-ray.com/api/userauth.php'
	collectionURL = 'http://m.blu-ray.com/api/collection.json.php?categoryid={category}&imgsz=1&session={session_id}'
	updateCollectableURL = 'http://m.blu-ray.com/api/updatecollectable.php'
	deleteCollectableURL = 'http://m.blu-ray.com/api/deletefromcollection.php?productid={product_id}&categoryid=21&session={session_id}'
	countriesURL = 'http://m.blu-ray.com/countries.json.php?_=1387933807086'
	priceTrackerURL = 'http://www.blu-ray.com/community/pricetracker.php'
	priceTrackerDeleteURL = 'http://www.blu-ray.com/community/pricetracker.php?action=delete&id={item_id}'
	priceTrackerEditURL = 'http://www.blu-ray.com/community/pricetracker.php?action=edit&id={item_id}'
	myPriceTrackerURL = 'http://m.blu-ray.com/api/pricetracker.php?session={session_id}&sortby=pricematch'
	coverURL = 'http://images.static-bluray.com/movies/covers/{procuct_id}_front.jpg'
	coverBackURL = 'http://images.static-bluray.com/movies/covers/{procuct_id}_back.jpg'
	pageARG = 'page=%s'
	
	addToCollectionURL = 'http://m.blu-ray.com/api/addtocollection.php'
	'''
	session:       c8bc1cdaf86f4bf848d8f8dc51e15c22
	productid:     1290
	categoryid:    7
	typeid:        1
	dateadded:     1388102245
	watched:       1
	description:   
	price:         0
	pricecomment:  
	dvc:           5
	'''
	
	categories = (	(7,'Blu-ray'),
					(21,'DVD'),
					(16,'PS3'),
					(29,'PS4'),
					(23,'XBox 360'),
					(30,'XBox One'),
					(26,'Wii'),
					(27,'Wii U'),
					(20,'Movies'),
					(24,'UltraViolet'),
					(28,'Amazon'),
					(31,'iTunes')
				)
	
	sections = (	('bluraymovies','Blu-ray'),
					('3d','3D Blu-Ray'),
					('dvdmovies','DVD'),
					('theatrical','Movies'),
					('uvmovies','UltraViolet'),
					('aivmovies','Amazon'),
					('itunesmovies','iTunes'),
					('ps3','PS3')
			)
				
	countries = [	{"c":"all","n":"All countries","u":"http://images.static-bluray.com/flags/global-transparent.png"},
					{"c":"us","n":"United States","u":"http://images3.static-bluray.com/flags/US.png"},
					{"c":"uk","n":"United Kingdom","u":"http://images3.static-bluray.com/flags/UK.png"},
					{"c":"ca","n":"Canada","u":"http://images3.static-bluray.com/flags/CA.png"},
					{"c":"de","n":"Germany","u":"http://images2.static-bluray.com/flags/DE.png"},
					{"c":"fr","n":"France","u":"http://images.static-bluray.com/flags/FR.png"},
					{"c":"au","n":"Australia","u":"http://images.static-bluray.com/flags/AU.png"},
					{"c":"nz","n":"New Zealand","u":"http://images.static-bluray.com/flags/NZ.png"},
					{"c":"za","n":"South Africa","u":"http://images4.static-bluray.com/flags/ZA.png"},
					{"c":"it","n":"Italy","u":"http://images2.static-bluray.com/flags/IT.png"},
					{"c":"es","n":"Spain","u":"http://images3.static-bluray.com/flags/ES.png"},
					{"c":"hk","n":"Hong Kong","u":"http://images4.static-bluray.com/flags/HK.png"},
					{"c":"kr","n":"South Korea","u":"http://images2.static-bluray.com/flags/KR.png"},
					{"c":"jp","n":"Japan","u":"http://images3.static-bluray.com/flags/JP.png"},
					{"c":"tw","n":"Taiwan","u":"http://images4.static-bluray.com/flags/TW.png"},
					{"c":"be","n":"Belgium","u":"http://images4.static-bluray.com/flags/BE.png"},
					{"c":"at","n":"Austria","u":"http://images2.static-bluray.com/flags/AT.png"},
					{"c":"ch","n":"Switzerland","u":"http://images4.static-bluray.com/flags/CH.png"},
					{"c":"br","n":"Brazil","u":"http://images.static-bluray.com/flags/BR.png"},
					{"c":"pt","n":"Portugal","u":"http://images.static-bluray.com/flags/PT.png"},
					{"c":"cn","n":"China","u":"http://images2.static-bluray.com/flags/CN.png"},
					{"c":"cz","n":"Czech Republic","u":"http://images2.static-bluray.com/flags/CZ.png"},
					{"c":"dk","n":"Denmark","u":"http://images4.static-bluray.com/flags/DK.png"},
					{"c":"fi","n":"Finland","u":"http://images4.static-bluray.com/flags/FI.png"},
					{"c":"gr","n":"Greece","u":"http://images2.static-bluray.com/flags/GR.png"},
					{"c":"hu","n":"Hungary","u":"http://images2.static-bluray.com/flags/HU.png"},
					{"c":"in","n":"India","u":"http://images4.static-bluray.com/flags/IN.png"},
					{"c":"mx","n":"Mexico","u":"http://images2.static-bluray.com/flags/MX.png"},
					{"c":"nl","n":"Holland","u":"http://images3.static-bluray.com/flags/NL.png"},
					{"c":"no","n":"Norway","u":"http://images2.static-bluray.com/flags/NO.png"},
					{"c":"pl","n":"Poland","u":"http://images.static-bluray.com/flags/PL.png"},
					{"c":"ru","n":"Russia","u":"http://images4.static-bluray.com/flags/RU.png"},
					{"c":"se","n":"Sweden","u":"http://images3.static-bluray.com/flags/SE.png"},
					{"c":"th","n":"Thailand","u":"http://images.static-bluray.com/flags/TH.png"},
					{"c":"tr","n":"Turkey","u":"http://images3.static-bluray.com/flags/TR.png"},
					{"c":"ua","n":"Ukraine","u":"http://images.static-bluray.com/flags/UA.png"}
				]
	
	def __init__(self):
		self.parser = None
		self.sessionID = ''
		self.user = None
		self.md5password = None
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
			cats.append((TR['pricetracker'],'','pricetracker'))
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
	
	def makeReviewSoup(self,req):
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
		return bs4.BeautifulSoup(fixed,self.parser,from_encoding=req.encoding)
	
	def getReview(self,url):
		req = self.session().get(url)
		soup = self.makeReviewSoup(req)
		if '/www.' in url:
			soup2 = self.makeReviewSoup(self.session().get(url + '?show=userreviews'))
			return GameReview(soup,soup2,url)
		else:
			return Review(soup,url)
	
	def getCollection(self,categories):
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
		if not self.apiLogin(): return
		items = []
		for category in categories:
			req = requests.get(self.collectionURL.format(category=category,session_id=self.sessionID))
			json = req.json()
			if not 'collection' in json:
				if not self.apiLogin(force=True): return []
				req = requests.get(self.collectionURL.format(category=category,session_id=self.sessionID))
				json = req.json()
				if not 'collection' in json: return []
			
			
			for i in json['collection']:
				items.append(CollectionResult(i,category))
				
		items.sort(key=lambda i: i.sortTitle)
		return items
	
	def search(self,terms,section='bluraymovies',country='all'):
		req = requests.get(self.searchURL.format(section=section,country=country.upper(),keyword=urllib.quote(terms)))
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
		
	def deleteCollectable(self,product_id):
		if not self.apiLogin(): return
		req = requests.get(self.deleteCollectableURL.format(product_id=product_id,session_id=self.sessionID))
		return not 'error' in req.json()
	
	def getPriceTracking(self):
		if not self.apiLogin(): return
		items = []
		req = requests.get(self.myPriceTrackerURL.format(session_id=self.sessionID))
		json = req.json()
		if not 'items' in json:
			if not self.apiLogin(force=True): return []
			req = requests.get(self.myPriceTrackerURL.format(session_id=self.sessionID))
			json = req.json()
			if not 'items' in json: return []
		for i in json['items']:
			items.append(PriceTrackingResult(i))
				
		return items
	
	def getTrackingIDWithURL(self,url):
		url = url.replace('://m.','://www.')
		soup = self.url2Soup(url)
		try:
			return soup.find('a',{'href':lambda x: 'pricetracker.php' in x and 'action=add' in x}).get('href').split('=')[-1]
		except:
			return ''
			
	def trackPrice(self,product_id,price,price_range=0,expiration=8,update_id=None):
		'''
		<input type="text" name="price_1" size="5" />
		<input type="text" name="pricerange_1" size="5" value="3" />
		<select name="expire_1" width="20%">
			<option value="1">1 week</option>
			<option value="2">1 month</option>
			<option value="3">3 months</option>
			<option value="4">6 months</option>
			<option value="5">12 months</option>
			<option value="6">3 years</option>
			<option value="7">5 years</option>
			<option value="8" selected>10 years</option>
		</select>
		<input type="hidden" name="action" value="add" />
		<input type="hidden" name="p" value="237173" />
		<input type="hidden" name="submit" value="1" />
		'''
		if not self.siteLogin(): return False
		if update_id:
			referer = 'http://www.blu-ray.com/community/pricetracker.php?action=edit&id=' + update_id
			data = {	'action':'edit',
						'submit':'1',
						'id':update_id,
						'price':price,
						'pricerange':price_range,
						'expire':expiration
				}
		else:
			referer = 'http://www.blu-ray.com/community/pricetracker.php?action=add&p=' + product_id
			data = {	'action':'add',
						'submit':'Track!',
						'p':product_id,
						'price_1':price,
						'pricerange_1':price_range,
						'expire_1':expiration
				}
		headers = {'Referer': referer}
		req = self.session().post(self.priceTrackerURL,data=data,headers=headers)
		return req.ok
	
	def unTrackPrice(self,item_id):
		if not self.siteLogin(): return False
		referer = 'http://www.blu-ray.com/community/pricetracker.php'
		headers = {'Referer': referer}
		req = self.session().get(self.priceTrackerDeleteURL.format(item_id=item_id),headers=headers)
		return req.ok
		
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
		self.session().post(self.siteLoginURL, {	'vb_login_username':self.user,
													'vb_login_password':'',
													's':'',
													'do':'login',
													'vb_login_md5password':self.md5password,
													'vb_login_md5password_utf':self.md5password
												})
		return self.siteLoggedOn()
		
	def siteLoggedOn(self):
		return 'bbsessionhash' in self.session().cookies
	
	def apiLogin(self,force=False):
		if not force and self.apiLoggedOn(): return True
		if not self.canLogin(): return False
		ak = 'cc32ae1a8a36f52ab0c79f030aa414fb'
		gcmregid = 'APA91bFQmwwEyckSUXeZ_oMygU77-L330OjNg3tFGbAtWQQPPmhU_w7JRJ0PFUSd1gyvkGgsrPCJVhGsrISTaMFeK9YnRlmkMGWmKcfdh7EQq2185W6MPniKxRE7Us6nSs1LrgqC2N_KJF8cMBKLtSiwjUFY5XG5Hw'
		req = requests.post(self.apiLoginURL,data={'u':self.user,'p':self.md5password,'ak':ak,'gcmregid':gcmregid})
		json = req.json()
		if 'session' in json: self.sessionID = json['session']
		return self.apiLoggedOn()
		
	def apiLoggedOn(self):
		return bool(self.sessionID)
	
	def canLogin(self):
		return self.user and self.md5password
	
		

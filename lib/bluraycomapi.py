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

def getGenreByID(ID):
	for name, label, gid in BlurayComAPI.genres:  # @UnusedVariable
		if gid == ID: return label
	return ''
	
class LoginError(Exception):
	def __init__(self,name,msg,code=0):
		Exception.__init__(self, msg)
		self.error = name
		self.code = code
		self.message = msg
		
class ResultItem:
	_resultType = 'None'
	_hr = '[COLOR FF606060]%s[/COLOR]' % ('_' * 200)
	headerColor = 'FF0080D0'
	
	def __init__(self):
		self.title = ''
		self.icon = ''
		self.ID = ''
		
	def start(self,soupData):
		self.processSoupData(soupData)
		return self
	
	def __str__(self):
		return '<%s=%s %s>' % (self._resultType,self.title,self.ID)
	
	def processSoupData(self,soupData):
		pass
	
	def convertTable(self,soup,table,sep=' '):
		if not table: return
		text = '[CR]' + self.getTableData(table, sep)
		tag = soup.new_tag('p')
		tag.string = text
		table.replaceWith(tag)
		
	def getTableData(self,table,sep=' '):
		if not table: return
		text = ''
		for tr in table.findAll('tr'):
			tds = []
			for td in tr.findAll('td'):
				tdtext = td.getText(strip=True).replace('[CR]',', ')
				if tdtext: tds.append(tdtext)
			text += sep.join(tds).strip() + '[CR]'
		return text
		
	def convertUL(self,soup,ul):
		text = '[CR]'
		for li in ul.findAll('li'):
			text += li.getText() + '[CR]%s[CR]' % self._hr
		tag = soup.new_tag('p')
		tag.string = text
		ul.replaceWith(tag)
		
	def setURL(self,url,catID):
		self.originalURL = url.replace('//ww.','//www.')
		self.url = self.originalURL
		if str(catID) in ('7','21'):
			self.url = self.originalURL.replace('www','m')
		
	def convertHeaders(self,soup,tag,h='h3',no_cr=False):
		for h3 in tag.findAll(h):
			for i in h3.findAll('img'):
				i.replaceWith(i.get('alt',''))
			h3r = soup.new_tag('p')
			if no_cr:
				h3r.string = '[COLOR %s][B]%s[/B][/COLOR]' % (self.headerColor,h3.getText().strip())
			else:
				h3r.string = '[CR][COLOR %s][B]%s[/B][/COLOR][CR]' % (self.headerColor,h3.getText().strip())
			h3.replaceWith(h3r)
			
	def convertBR(self,tag):
		for t in tag.findAll('br'): t.insert_after('[CR]')
		
	def replaceFlags(self,soup,tag):
		for img in tag.findAll('img',{'src':lambda x: x and '/flags/' in x}):
			new = soup.new_tag('span')
			new.string = '(%s) ' % img.get('src','').rsplit('.',1)[0].rsplit('/',1)[-1]
			img.replaceWith(new)
		
	_flagCodeRE = re.compile('/flags/([\w-]+)\.png')
	def convertFlagImage(self,url):
		try:
			code = self._flagCodeRE.search(url).group(1).lower()
			if code == 'global-transparent': code = 'all'
			for i in BlurayComAPI.countries:
				if code == i['c']:
					return i['u']
			raise Exception('Country Not Found')
		except:
			pass
		return url
	
	_excessiveNL = re.compile('(?:\s*\[CR\]\s*){3,}')
	def cleanWhitespace(self,text):
		text = text.strip()
		while text.startswith('[CR]'): text = text[4:].lstrip()
		while text.endswith('[CR]'): text = text[:-4].rstrip()
		text = self._excessiveNL.sub('[CR][CR]',text)	
		return re.sub('\[CR\]\s+','[CR]',text)
	
	_URLRatingRE = re.compile('/b(\d0?)\.jpg')
	def extractRatingNumber(self,url):
		try:
			return self._URLRatingRE.search(url).group(1)
		except:
			return '0'
	
	_percentRE = re.compile('(?<!\d)(1?\d{1,2}%)')
	def colorPercents(self,text):
		return self._percentRE.sub(r'[COLOR FFFFCCCC]\1[/COLOR]',text)
	
	_priceRE = re.compile('(\$\d*\.\d{2})')
	def colorPrices(self,text):
		return self._priceRE.sub(r'[COLOR FFCCFFCC]\1[/COLOR]',text)
	
	_ratingRE = re.compile('(?<!\d)(1?\d\.\d)(?!\d)')
	def colorRatings(self,text):
		return self._ratingRE.sub(r'[COLOR FFCCCCFF]\1[/COLOR]',text)
	
class ReviewsResult(ResultItem):
	_resultType = 'ReviewsResult'
	
	def __init__(self):
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
		self.categoryID = ''
		self.genreIDs = []
		self.sortTitle = ''
		self.runtime = 0
		self.watched = False
		ResultItem.__init__(self)
		
	def processSoupData(self,soupData):
		self.title = soupData.find('h3').getText().strip()
		flagImg = soupData.find('img',{'src':lambda x: '/flag/' in x})
		if flagImg: self.flagImage = self.convertFlagImage(flagImg.get('src',''))
		images = soupData.findAll('img')
		self.icon = images[0].get('src')
		self.rating = images[-1].get('alt')
		self.ratingImage = 'rating/script-bluray-com-brating_%s.png' % self.extractRatingNumber(images[-1].get('src'))
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
	def __init__(self,catID):
		ReviewsResult.__init__(self)
		self.categoryID = catID
		
	def processSoupData(self,json):
		self.title = json.get('title','')
		self.ID = json.get('pid','')
		self.trackingID = json.get('gpid','')
		self.setURL(json.get('url',''), self.categoryID)
		if not self.ID: self.ID = self.url.strip('/').rsplit('/')[-1]
		catID = str(self.categoryID)
		if catID in BlurayComAPI.coverURLs:
			self.icon = BlurayComAPI.coverURLs[catID].format(id=self.ID,size='medium')
		else:
			self.icon = json.get('cover',json.get('coverurl0',''))
		if catID == '24': #Ultraviolet urls don't translate properly
			urlName = self.url.rsplit('-Blu-ray/')[0].rsplit('/')[-1]
			self.url = BlurayComAPI.pageURLs[catID].format(urlname=urlName,id=self.ID)
		elif catID in BlurayComAPI.pageURLs:
			self.url = BlurayComAPI.pageURLs[catID].format(id=self.ID)
		self.flagImage = self.convertFlagImage(json.get('flag',''))
		rating = json.get('rating','')
		try:
			rating = int(rating)
			self.ratingImage = 'rating/script-bluray-com-brating_%s.png' % rating
			self.rating = 'Overall: %.1f of 5' % (rating/2.0)
		except:
			try:
				self.ratingImage = 'rating/script-bluray-com-stars_%s.png' % (int((round(float(rating) * 2)/2)*10) or '0')
				self.rating = 'Rating: %.1f' % float(rating)
			except:
				pass
		self.info = json.get('year','') + ' | ' + json.get('reldate','')
		
		
class SiteSearchResult(ReviewsResult):
	def __init__(self,catID):
		ReviewsResult.__init__(self)
		self.categoryID = catID
		
	def processSoupData(self,soupData):
		self.title = soupData.find('h3').getText(strip=True)
		self.icon = soupData.find('img').get('src').replace('_small.','_medium.')
		self.setURL(soupData.find('a').get('href'), self.categoryID)
		self.info = soupData.find('table').getText(strip=True)
		dtable = soupData.findAll('table')[-1]
		self.description = self.getTableData(dtable, ': ')
		ratingImage = soupData.find('img',{'src':lambda x: 'rating' in x})
		if ratingImage:
			self.rating = ratingImage.get('alt','')
			self.ratingImage = 'rating/script-bluray-com-brating_%s.png' % self.extractRatingNumber(ratingImage.get('src'))
		flagImg = soupData.find('img',{'src':lambda x: '/flags/' in x})
		if flagImg: self.flagImage = self.convertFlagImage(flagImg.get('src',''))
		
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
	def __init__(self,categoryid):
		ReviewsResult.__init__(self)
		self.categoryID = categoryid
		self.originalURL = ''
		self.watched = False
		self.json = {}
		
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
		self.setURL(json.get('url'), self.categoryID)
		self.sortTitle = json.get('titlesort',self.title)
		self.genreIDs = json.get('genreids','').split(',')
		try:
			self.runtime = int(json.get('runtime','0'))
		except:
			self.runtime = 0

		rating = json.get('rating','')
		if rating:
			try:
				self.ratingImage = 'rating/script-bluray-com-stars_%s.png' % (int((round(float(rating) * 2)/2)*10) or '0')
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
	def __init__(self):
		ReviewsResult.__init__(self)
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
			
	def processSoupData(self,json):
		self.json = json
		self.ID = json.get('pid','')
		self.title = json.get('title','')
		self.icon = json.get('coverurl0','').replace('_small.','_medium.')
		self.categoryID = json.get('categoryid','')
		self.setURL(json.get('url'), self.categoryID)
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
	def __init__(self,url):
		ReviewsResult.__init__(self)
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
		self.imdb = ''
		self.imdbVideos = []
		self.url = url
		self.ID = self.url.strip('/').rsplit('/')[-1]
		
	def processSoupData(self,soupData):
		flagImg = soupData.find('img',{'src':lambda x: 'flags' in x})
		if flagImg: self.flagImage = self.convertFlagImage(flagImg.get('src',''))
		
		self.owned = bool(soupData.find('a',{'href':lambda x: '/collection.php' in x}))
		
		self.getImages(soupData)
			
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
			self.convertBR(reviewSoup)
			self.convertTable(soupData, reviewSoup.find('table'))
			self.review = self.colorRatings(self.cleanWhitespace(reviewSoup.getText()))
			
		price_rating = soupData.findAll('div',{'class':'content2'})
		self.convertHeaders(soupData, price_rating[0])
		self.convertBR(price_rating[0])
		self.price = self.colorPrices(self.cleanWhitespace(price_rating[0].getText()))
		if len(price_rating) > 1:
			self.convertHeaders(soupData, price_rating[1])
			self.convertTable(soupData, price_rating[1].find('table'),': ')
			self.blurayRating = self.colorRatings(self.cleanWhitespace(price_rating[1].getText()))
			
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
			
	def getImages(self,soupData):
		img = soupData.find('img',{'id':'reviewScreenShot'})
		if not img: return
		base = img.get('src','').replace('1.jpg','%d.jpg')
		try:
			test = requests.get(self.url.replace('//m.','//www.')).text
			count = int(re.search('<td id="menu_screenshots_num"[^>]*?><small>\((\d+)\)</small>',test).group(1)) + 1
		except:
			count = 11
			
		for i in range(1,count):
			src = base % i
			p1080 = src.replace('.jpg','_1080p.jpg')
			self.images.append((src,p1080))
		
		for i in soupData.findAll('img',{'id':'reviewScreenShot'}):
			src = i.get('src','')
			idx = src.rsplit('.',1)[0].split('_',1)[-1]
			tag = soupData.new_tag('span')
			tag.string = '[CR][COLOR FFA00000]IMAGE %s[/COLOR][CR]' % idx
			i.insert_before(tag)
			
	def processOverview(self,soupData,section):
		self.convertHeaders(soupData, section)
		self.convertTable(soupData, section.find('table'),sep=': ')
		self.overview = self.colorPercents(self.cleanWhitespace(section.getText()))
		
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
			
class SiteReview(Review):
	_resultType = 'GameReview'
	def __init__(self, reviewSoupData, url):
		Review.__init__(self, url)
		self.reviewSoupData = reviewSoupData
		
	def processSoupData(self,soupData):
		self.owned = bool(soupData.find('a',{'href':lambda x: x and ('/collection.php' in x) and ('action=showcategory' in x)}))		
		self.title = soupData.find('title').getText(strip=True)
		
		flagImg = soupData.find('img',{'src':lambda x: 'flags' in x})
		if flagImg: self.flagImage = self.convertFlagImage(flagImg.get('src',''))
		
		subheading = soupData.find('span',{'class':'subheading'})
		if subheading: self.subheading1 = subheading.getText().strip()
		
		coverImg = soupData.find('img',{'id':'productimage','src': lambda x: not '.gif' in x})
		if not coverImg: coverImg = soupData.find('meta',{'property':lambda x: x and ('image' in x)})
		if not coverImg: coverImg = soupData.find('meta',{'itemprop':lambda x: x and ('image' in x)})
		
		if coverImg:
			self.coverImage = coverImg.get('src',coverImg.get('content',''))
# 			self.coverFront = self.coverImage.replace('_medium','_large')
# 			self.coverBack = self.coverFront.replace('1_large', '2_large')
			
		for p in soupData.findAll('p'):
			p.replaceWith(p.getText() + '[CR]')
		
		try:
			self.imdb = soupData.find('a',{'href':lambda x: x and 'www.imdb.com/title/' in x}).get('href','')
		except:
			pass
		if self.imdb: self.imdbVideos = getIMDBVideoIDs(self.imdb)
		
		specH3 = soupData.find('h3',text='Specifications')
		if specH3:
			for sibling in specH3.next_siblings:
				if sibling.name == 'table':
					self.convertHeaders(soupData, sibling, 'h5')
					for table in sibling.findAll('table'):
						self.convertTable(soupData, table, ': ')
					self.specifications = ('[COLOR %s][B]Specifications[/B][/COLOR][CR][CR]' % self.headerColor) + self.cleanWhitespace(sibling.getText())
					break
		else:
			try:
				td = soupData.find('span',{'class':'subheading'},text='Video').parent
				for span in td.findAll('span',{'class':'subheading'}): span.string = '[COLOR %s][B]%s[/B][/COLOR][CR]' % (self.headerColor,span.string)
				self.specifications = ('[COLOR %s][B]Specifications[/B][/COLOR][CR][CR]' % self.headerColor) + self.cleanWhitespace(td.getText())
			except:
				pass
		
		if not self.specifications:
			table = soupData.find('span',{'class':'subheading'}).find_next_sibling('table')
			if table:
				text = ''
				for sib in table.find('div',{'id':'showdelete'}).next_siblings:
					if sib.string == 'Links':
						break
					elif not sib.name:
						t = sib.string.strip()
						if t: text += t + ' '
					else:
						self.convertHeaders(soupData, sib)
						self.replaceFlags(soupData, sib)
						if sib.name == 'h3':
							text += '[COLOR %s][B]%s[/B][/COLOR] ' % (self.headerColor,sib.getText(strip=True))
						elif sib.name == 'br':
							text += '[CR]'
						else:
							last = ''
							for c in sib.descendants:
								if last in ('br','div','tr'):
									text += '[CR]'
								if c.name == 'div':
									text += '[CR]'
								elif not c.name and c.string:
									t = c.string.strip()
									if t:
										if c.parent.name == 'small': t = '[COLOR FF808080]%s[/COLOR]' % t
										text += t
										if not c.parent.name == 'td' and not c.parent.parent.name == 'td': text += ' '
								elif c.name == 'td' and c.previous_sibling and c.previous_sibling.name == 'td' and not c.previous_sibling.find('br'):
									text += ': '
								last = c.name
								
				self.specifications = self.cleanWhitespace(text)
		self.specifications = self.colorPercents(self.specifications)

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
			self.price = self.colorPrices(price)
		else:
			try:
				td = soupData.find('span',{'class':'subheading'},text='iTunes store').parent
				for span in td.findAll('span',{'class':'subheading'}): span.string = '[COLOR %s][B]%s[/B][/COLOR][CR]' % (self.headerColor,span.string)
				text = ''
				for c in td.children:
					if c.name == 'table':
						break
					elif c.name in ('div','br'):
						text += '[CR]'
					elif not c.name:
						t = c.string.strip()
						if t: text += t + ' '
					else:
						t = c.getText(strip=True)
						if t: text += t + ' '
					
						
				self.price = ('[COLOR %s][B]Price[/B][/COLOR][CR][CR]' % self.headerColor) + self.cleanWhitespace(text)
			except:
				pass
		try:
			for graph in soupData.findAll('img',{'onmouseover':lambda x: x and 'pricehistory.php' in x}):
				img = re.search("'(http://[^']*?)'",graph.get('onmouseover')).group(1)
				self.historyGraphs.append((img,img))
		except:
			pass
		
		rating = soupData.find('div',{'id':'ratingscore'}) or ''
		if rating:
			if rating.string == '0':
				rating = ''
			else:
				rating = 'Rating: %s[CR][CR]' % rating.string
				
		start = soupData.find('a',{'href':lambda x: x and '&reviewerid=' in x})
		if start:
			review = start.parent.getText()
			idx = 1
			for sib in start.parent.next_siblings:
				if sib.name == 'a' and 'history' in sib.get('rel',''):
					break
				elif sib.name and sib.find('img',{'src':lambda x: not '.gif' in x}):
					url = sib.find('img').get('src','')
					self.images.append((url,url.replace('_tn.','_original.')))
					review += '[CR][COLOR FFA00000]IMAGE %s[/COLOR][CR]' % idx
					idx += 1
				elif sib.name == 'br':
					review += '[CR]'
				elif sib.name:
					review += sib.getText()
				else:
					review += sib.string
			self.review = rating + self.cleanWhitespace(review.replace(u'\xbb','')) + '[CR][CR]'
		self.getReviews()
		
		images = soupData.findAll('img',{'src':lambda x: '_mini.jpg' in x})
		if images:
			for i in images:
				src = i.get('src')
				if src:
					self.images.append((src.replace('_mini.','_medium.'),src.replace('_mini.','_original.')))
		else:
			self.images.append((self.coverImage,self.coverImage.replace('_medium.','_front.')))
			
		for i in soupData.findAll('img',{'width':'80','src':lambda x: x and not x.endswith('.gif')}):
			self.similarTitles.append((i.parent.get('href',''),i.get('src',''),i.get('title')))		

		for i in soupData.findAll('img',{'width':'180','src':lambda x:x and x.endswith('_tn.jpg')}):
			src = i.get('src','')
			self.images.append((src.replace('_tn.','.'),src.replace('_tn.','_1080p.')))
			
	def getReviews(self):
		reviewH3 = self.reviewSoupData.find('h3',text='Post a review')
		if reviewH3:
			for tag in reviewH3.previous_siblings:
				if tag.name == 'table':
					tables = [tag]
					for sib in tag.previous_siblings:
						if sib.name == 'table':
							if sib.form: break
							tables.insert(0, sib)
					if tables:
						if self.review: self.review += '[B]%s[/B][CR][CR]'  % ('_' * 200)
						self.review += '[COLOR %s][B]User Reviews[/B][/COLOR]' % self.headerColor
					for t in tables:
						self.review += '[CR]' + self._hr + '[CR]' +  self.getUserReview(t)
					break
				elif tag.string and 'No user reviews' in tag.string:
					self.review += 'No Reviews'
					break
		else:
			try:
				rev = self.reviewSoupData.find('div',{'id':'movie_info'})
				end = rev.find('a',{'rel':'history'})
				if end: end.extract()
				self.convertHeaders(self.reviewSoupData, rev,no_cr=True)
				self.convertBR(rev)
				self.review = self.cleanWhitespace(rev.getText().replace(u'\xbb',''))
			except:
				pass
		self.review = self.colorRatings(self.review)
		del self.reviewSoupData
		
	def getUserReview(self,table):
		self.convertHeaders(self.reviewSoupData, table, 'h5',no_cr=True)
		self.convertBR(table)
		return self.cleanWhitespace(table.getText().strip())

def getIMDBVideoIDs(url):
	#'http://www.imdb.com/video/imdb/vi2165155865/imdbvideo?format=720p'
	try:
		headers = {'User-Agent':'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.17 (KHTML, like Gecko) Chrome/24.0.1312.57 Safari/537.17'}
		soup = bs4.BeautifulSoup(requests.get(url,headers=headers).text)
		try:
			defImage = soup.find('meta',{'property':'og:image'}).get('content','')
		except:
			defImage = ''
		IDs = []
		for i in soup.findAll('a',{'data-video':lambda x: x}):
			if 'offsite?' in i.get('href',''): continue
			ID = i.get('data-video')
			img = i.find('img')
			tn = img and img.get('loadlate') or defImage
			if ID: IDs.append((ID,tn))
		return IDs
	except:
		pass
	return []

def playIMDBVideo(ID):
	try:
		import xbmc, xbmcgui
		#formats: 720p etc
		url = 'http://www.imdb.com/video/imdb/{video_id}/imdbvideo?format={format}'.format(video_id=ID,format='720p')
		headers = {'User-Agent':'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.17 (KHTML, like Gecko) Chrome/24.0.1312.57 Safari/537.17'}
		flvURL = re.findall('"url":"([^"]*)"',requests.get(url,headers=headers).text)[0]
		title = ''
		thumbnail = ''
		plot = ''
		listitem = xbmcgui.ListItem(title, iconImage="", thumbnailImage=thumbnail)
		# set the key information
		listitem.setInfo('video', {'title': title, 'label': title, 'plot': plot, 'plotOutline': plot})
		xbmc.Player().play(flvURL, listitem)
	except:
		LOG('ERROR: playIMDBVideo()')
	

def removeColorTags(text):
	return re.sub('\[/?COLOR[^\]]*?\]','',text)

class BlurayComAPI:
	reviewsURL = 'http://m.blu-ray.com/movies/reviews.php'
	releasesURL = 'http://m.blu-ray.com/movies'
	dealsURL = 'http://m.blu-ray.com/deals/index.php'
	searchURL = 'http://m.blu-ray.com/quicksearch/search.php?userid=0&country={country}&section={section}&keyword={keyword}&_={time}'
	apiSearchURL = 'http://m.blu-ray.com/api/quicksearch.php?country={country}&section={section}&keyword={keyword}&ak={ak}&session={session_id}'
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
					(20,'Theatrical'),
					(24,'UltraViolet'),
					(28,'Amazon'),
					(31,'iTunes')
				)
	
	sections = (	('bluraymovies','Blu-ray',7),
					('3d','3D Blu-Ray',0),
					('dvdmovies','DVD',21),
					('theatrical','Theatrical',20),
					('uvmovies','UltraViolet',24),
					('aivmovies','Amazon',28),
					('itunesmovies','iTunes',31),
					('16','PS3',16),
					('23','XBox 360',23),
					('26','Wii',26),
					('29','PS4',29),
					('30','XBox One',30),
					('27','Wii U',27)
			)
	
	coverURLs = {	'16':'http://images.static-bluray.com/products/16/{id}_1_medium.jpg',
					'28':'http://images.static-bluray.com/movies/aivcovers/{id}_{size}.jpg',
					'31':'http://images.static-bluray.com/movies/itunescovers/{id}_{size}.jpg',
					'24':'http://images.static-bluray.com/movies/uvcovers/{id}_{size}.jpg'
				}
			
	pageURLs = {	'20':'http://www.blu-ray.com/X/{id}/',
					'28':'http://www.blu-ray.com/aiv/X-AIV/{id}/',
					'31':'http://www.blu-ray.com/itunes/X-iTunes/{id}/',
					'24':'http://www.blu-ray.com/uv/{urlname}-UltraViolet/{id}/'
				}
	
	siteSearchURL = 'http://www.blu-ray.com/{platform}/search.php'
	siteSearchPlatforms = {	'29':'ps4', '23':'xbox360', '30':'xboxone', '26':'wii', '27':'wiiu','16':'ps3'}
	
	countries = [	{"c":"all","n":"All countries","u":"flags/ALL.png"},
					{"c":"us","n":"United States","u":"flags/US.png"},
					{"c":"uk","n":"United Kingdom","u":"flags/GB.png"},
					{"c":"ca","n":"Canada","u":"flags/CA.png"},
					{"c":"de","n":"Germany","u":"flags/DE.png"},
					{"c":"fr","n":"France","u":"flags/FR.png"},
					{"c":"au","n":"Australia","u":"flags/AU.png"},
					{"c":"nz","n":"New Zealand","u":"flags/NZ.png"},
					{"c":"za","n":"South Africa","u":"flags/ZA.png"},
					{"c":"it","n":"Italy","u":"flags/IT.png"},
					{"c":"es","n":"Spain","u":"flags/ES.png"},
					{"c":"hk","n":"Hong Kong","u":"flags/HK.png"},
					{"c":"kr","n":"South Korea","u":"flags/KR.png"},
					{"c":"jp","n":"Japan","u":"flags/JP.png"},
					{"c":"tw","n":"Taiwan","u":"flags/TW.png"},
					{"c":"be","n":"Belgium","u":"flags/BE.png"},
					{"c":"at","n":"Austria","u":"flags/AT.png"},
					{"c":"ch","n":"Switzerland","u":"flags/CH.png"},
					{"c":"br","n":"Brazil","u":"flags/BR.png"},
					{"c":"pt","n":"Portugal","u":"flags/PT.png"},
					{"c":"cn","n":"China","u":"flags/CN.png"},
					{"c":"cz","n":"Czech Republic","u":"flags/CZ.png"},
					{"c":"dk","n":"Denmark","u":"flags/DK.png"},
					{"c":"fi","n":"Finland","u":"flags/FI.png"},
					{"c":"gr","n":"Greece","u":"flags/GR.png"},
					{"c":"hu","n":"Hungary","u":"flags/HU.png"},
					{"c":"in","n":"India","u":"flags/IN.png"},
					{"c":"mx","n":"Mexico","u":"flags/MX.png"},
					{"c":"nl","n":"Holland","u":"flags/NL.png"},
					{"c":"no","n":"Norway","u":"flags/NO.png"},
					{"c":"pl","n":"Poland","u":"flags/PL.png"},
					{"c":"ru","n":"Russia","u":"flags/RU.png"},
					{"c":"se","n":"Sweden","u":"flags/SE.png"},
					{"c":"th","n":"Thailand","u":"flags/TH.png"},
					{"c":"tr","n":"Turkey","u":"flags/TR.png"},
					{"c":"ua","n":"Ukraine","u":"flags/UA.png"}
				]
	
	countries_n = [	{"c":"all","n":"All countries","u":"http://images.static-bluray.com/flags/global-transparent.png"},
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
	
	genres = [	('all', u'-',''),
				('action', u'Action', '1'),
				('adventure', u'Adventure', '2'),
				('animation', u'Animation', '3'),
				('anime', u'Anime', '4'),
				('biography', u'Biography', '5'),
				('comedy', u'Comedy', '6'),
				('comicbook', u'Comic book', '35'),
				('comingofage', u'Coming of age', '43'),
				('crime', u'Crime', '7'),
				('blackcomedy', u'Dark humor', '29'),
				('documentary', u'Documentary', '8'),
				('drama', u'Drama', '9'),
				('epic', u'Epic', '39'),
				('erotic', u'Erotic', '33'),
				('family', u'Family', '10'),
				('fantasy', u'Fantasy', '11'),
				('filmnoir', u'Film-Noir', '12'),
				('foreign', u'Foreign', '36'),
				('heist', u'Heist', '44'),
				('history', u'History', '13'),
				('holiday', u'Holiday', '42'),
				('horror', u'Horror', '14'),
				('imaginary', u'Imaginary', '31'),
				('martialarts', u'Martial arts', '34'),
				('melodrama', u'Melodrama', '38'),
				('music', u'Music', '15'),
				('musical', u'Musical', '16'),
				('mystery', u'Mystery', '17'),
				('nature', u'Nature', '18'),
				('other', u'Other', '19'),
				('period', u'Period', '41'),
				('psychologicalthriller', u'Psychological thriller', '30'),
				('romance', u'Romance', '20'),
				('scifi', u'Sci-Fi', '21'),
				('short', u'Short', '22'),
				('sport', u'Sport', '23'),
				('supernatural', u'Supernatural', '32'),
				('surreal', u'Surreal', '37'),
				('teen', u'Teen', '28'),
				('thriller', u'Thriller', '25'),
				('war', u'War', '26'),
				('western', u'Western', '27')
			]
	
	siteEncoding = 'iso-8859-2'
		
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
		req.encoding = self.siteEncoding
		return self.getSoup(req.text)
	
	def getSoup(self,text):
		try:
			soup = bs4.BeautifulSoup(text, 'lxml', from_encoding=self.siteEncoding)
			LOG('Using: lxml parser')
			return soup
		except:
			pass
		try:
			soup = bs4.BeautifulSoup(text, 'html5lib', from_encoding=self.siteEncoding)
			LOG('Using: html5lib parser')
			return soup
		except:
			pass
		LOG('Using: html.parser parser')
		return bs4.BeautifulSoup(text, self.parser, from_encoding=self.siteEncoding)
	
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
				res = ReleasesResult().start(i)
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
			items.append(DealsResult().start(i))
		return (items,self.getPaging(soup))
	
	def getReviews(self,page=''):
		if page:
			page = '?' + self.pageARG % page
		else:
			page = ''
		soup = self.url2Soup(self.reviewsURL + page)
		items = []
		for i in soup.findAll('li',{'data-role':lambda x: not x}):
			items.append(ReviewsResult().start(i))
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
		fixed = fixed.replace(u'\x97',' - ').replace(u'\x92',u'\u2019').replace(u'\x93',u'\u201c').replace(u'\x94',u'\u201d')
		fixed = re.sub('<i>(?i)','[I]',fixed)
		fixed = re.sub('</i>(?i)',' [/I]',fixed)
		#fixed = re.sub('<br[^>]*?>(?i)','[CR]',fixed)
		return bs4.BeautifulSoup(fixed,self.parser,from_encoding=self.siteEncoding)
	
	def getReview(self,url,catID):
		if str(catID) == '20':
			req = self.session().get(url + '?show=preview')
		else:
			req = self.session().get(url)
		
		soup = self.makeReviewSoup(req)
		if '/www.' in url:
			soup2 = self.makeReviewSoup(self.session().get(url + '?show=userreviews'))
			return SiteReview(soup2,url).start(soup)
		else:
			return Review(url).start(soup)
	
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
				items.append(CollectionResult(category).start(i))
				
		items.sort(key=lambda i: i.sortTitle)
		return items
	
	def getCatIDFromSection(self,section):
		for s,label,catID in self.sections:  # @UnusedVariable
			if s == section:
				return catID
			
	def search(self,terms,section='bluraymovies',country='all'):
		if section.isdigit():
			url = self.siteSearchURL.format(platform=self.siteSearchPlatforms.get(str(section)))
			req = requests.post(url,data={'general_model':terms,'action':'search','c':section,'searchsubmit':'Search'},headers={'Referer':url})
			results = []
			soup = self.getSoup(req.text)
			for table in soup.find('form',{'id':'compareform'}).findAll('table',recursive=False):
				results.append(SiteSearchResult(section).start(table))
		else:
			url = self.searchURL.format(section=section,country=country.upper(),keyword=urllib.quote(terms),time=str(int(time.time()*1000)))
			req = requests.get(url)
			results = []
			for i in req.json().get('items',[]):
				results.append(ReviewsResultJSON(self.getCatIDFromSection(section)).start(i))
				
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
			items.append(PriceTrackingResult().start(i))
				
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
		self.sessionID = ''
		if 'session' in json:
			self.sessionID = json['session']
		else:
			if str(json.get('error')) == '4':
				raise LoginError('userpass','Bad username or password')
			else:
				raise LoginError('unknown','Unknown',code=-1)
		return self.apiLoggedOn()
		
	def apiLoggedOn(self):
		return bool(self.sessionID)
	
	def canLogin(self):
		return self.user and self.md5password
	
		

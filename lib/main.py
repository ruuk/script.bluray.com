import os, sys, shutil, requests
import xbmc, xbmcgui, xbmcaddon
import bluraycomapi

ADDON = xbmcaddon.Addon()
T = ADDON.getLocalizedString

CACHE_PATH = os.path.join(xbmc.translatePath(ADDON.getAddonInfo('profile')),'cache')

if not os.path.exists(CACHE_PATH): os.makedirs(CACHE_PATH)

API = None
LAST_SEARCH = ''

def LOG(msg):
	print 'Blu-ray.com: %s' % msg
bluraycomapi.LOG = LOG
	
def imageToCache(src,name):
	response = requests.get(src, stream=True)
	target = os.path.join(CACHE_PATH,name)
	with open(target, 'wb') as out_file:
		shutil.copyfileobj(response.raw, out_file)
	del response
	return target

class BaseWindowDialog(xbmcgui.WindowXMLDialog):
	def __init__(self):
		self.loading = None
		self._closing = False
		self._winID = ''
		
	def onInit(self):
		self._winID = xbmcgui.getCurrentWindowDialogId()
		xbmcgui.WindowXMLDialog.onInit(self)
		
	def loadingOn(self):
		if not self.loading: return
		self.setProperty('loading','1')
		
	def loadingOff(self):
		if not self.loading: return
		self.setProperty('loading','0')
		
	def setProperty(self,key,value):
		if self._closing: return
		xbmcgui.Window(self._winID).setProperty(key,value)
		xbmcgui.WindowXMLDialog.setProperty(self,key,value)
		
	def doClose(self):
		self._closing = True
		self.close()
	
class BluRayCategories(xbmcgui.WindowXML):
	def __init__(self,*args,**kwargs):
		xbmcgui.WindowXML.__init__(self)
	
	def onInit(self):
		self.catList = self.getControl(100)
		self.showCategories()
		
	def showCategories(self):
		items = []
		for label, icon, ID in API.getCategories():
			item = xbmcgui.ListItem(label=label,iconImage=icon)
			item.setProperty('id',ID)
			items.append(item)
		self.catList.addItems(items)
		self.setFocus(self.catList)
		
	def onClick(self,controlID):
		if controlID == 100:
			item = self.catList.getSelectedItem()
			if not item: return
			if item.getProperty('id') == 'reviews':
				openReviewsWindow()
			elif item.getProperty('id') == 'releases':
				openReviewsWindow(mode='RELEASES')
			elif item.getProperty('id') == 'deals':
				openReviewsWindow(mode='DEALS')
			elif item.getProperty('id') == 'collection':
				openReviewsWindow(mode='COLLECTION')
			elif item.getProperty('id') == 'pricetracker':
				openReviewsWindow(mode='PRICETRACKER')
			elif item.getProperty('id') == 'search':
				openReviewsWindow(mode='SEARCH')
				
class BluRayReviews(BaseWindowDialog):
	def __init__(self,*args,**kwargs):
		BaseWindowDialog.__init__(self)
		self.mode = kwargs.get('mode')
		self.currentResults = []
		self.idxOffset = 0
		self.hasSearched = False
		self.lastCategory=None
		self.filterLetter = ''
		self.filterGenre1 = ''
		self.filterGenre2 = ''
		self.filterGenre3 = ''
		self.filterRuntime = 0
		self.filterWatched = None
		self.filterGenre1Exclude = False
		self.filterGenre2Exclude = False
		self.filterGenre3Exclude = False
		self.filterString = ''
	
	def onInit(self):
		BaseWindowDialog.onInit(self)
		self.reviewList = self.getControl(101)
		self.loading = self.getControl(149)
		self.showReviews()
	
	def refresh(self,page=0,category=None,filterChange=False):
		self.reviewList.reset()
		self.showReviews(page=page,category=category,filterChange=filterChange)
		
	def getCollectionCategories(self,category=None):
		if category is not None:
			default = category
		else:
			default = getSetting('default_collection',0)
			if default > 0: default = API.categories[default-1][0]
		if default == 0:
			cats = []
			for ID,cat in API.categories:  # @UnusedVariable
				if getSetting('all_cat_%d' % ID,False): cats.append(ID)
			return cats
		else:
			return [default]
	
	def getCollectionCategoriesToShow(self):
		cats = []
		for ID,cat in API.categories:
			if getSetting('used_cat_%d' % ID,False): cats.append((ID,cat))
		return cats

	def showReviews(self,page=0,category=None,filterChange=False):
		self.setProperty('filterstring',self.filterString)
		self.loadingOn()
		try:
			paging = (None,None)
			if self.mode == 'SEARCH':
				self.loadingOff()
				w = openWindow(BluRaySearch,'bluray-com-search.xml',return_window=True)
				self.loadingOn()
				if w.canceled:
					if not self.hasSearched: self.doClose()
					return
				if not w.keywords:
					if not self.hasSearched: self.doClose()
					return
				results = API.search(w.keywords,w.section,w.country)
				del w
				if not results:
					xbmcgui.Dialog().ok(T(32008),T(32009))
					if self.hasSearched: return
					self.doClose()
					return
				self.hasSearched = True
				self.reviewList.reset()
			elif self.mode == 'RELEASES':
				results = API.getReleases()
			elif self.mode == 'DEALS':
				results, paging = API.getDeals(page)
			elif self.mode == 'COLLECTION':
				if filterChange:
					results = self.currentResults
				else:
					try:
						results = API.getCollection(categories=self.getCollectionCategories(category))
					except bluraycomapi.LoginError, e:
						error = 'Unknown'
						if e.error == 'userpass': error = 'Bad Blu-ray.com name or password.'
						xbmcgui.Dialog().ok('Error','Login Error:','',error)
						return
				self.lastCategory = category
				self.currentResults = results
			elif self.mode == 'PRICETRACKER':
				try:
					results = API.getPriceTracking()
				except bluraycomapi.LoginError,e:
					error = 'Unknown'
					if e.error == 'userpass': error = 'Bad Blu-ray.com name or password.'
					xbmcgui.Dialog().ok('Error','Login Error:','',error)
					return
				self.currentResults = results
			else:
				results, paging = API.getReviews(page)
			items = []
			if paging[0]:
				item = xbmcgui.ListItem(label=T(32005),iconImage='')
				item.setProperty('paging','prev')
				item.setProperty('page',paging[0])
				items.append(item)
				self.idxOffset = 1
				
			for i in results:
				if i._section: items.append(self.addSection(i))
				if not self.filter(i):
					continue
				item = xbmcgui.ListItem(label=i.title,iconImage=i.icon)
				self.setUpItem(item, i)
				items.append(item)
				
			if paging[1]:
				item = xbmcgui.ListItem(label=T(32006),iconImage='')
				item.setProperty('paging','next')
				item.setProperty('page',paging[1])
				items.append(item)
				
			self.reviewList.addItems(items)
			self.setFocus(self.reviewList)
		finally:
			self.loadingOff()

	def filter(self,i):
		if self.filterGenre1:
			if self.filterGenre1Exclude:
				if self.filterGenre1 in i.genreIDs: return False
			else:
				if not self.filterGenre1 in i.genreIDs: return False
		if self.filterGenre2:
			if self.filterGenre2Exclude:
				if self.filterGenre2 in i.genreIDs: return False
			else:
				if not self.filterGenre2 in i.genreIDs: return False
		if self.filterGenre3:
			if self.filterGenre3Exclude:
				if self.filterGenre3 in i.genreIDs: return False
			else:
				if not self.filterGenre3 in i.genreIDs: return False
		if self.filterLetter and not (i.sortTitle or i.title).startswith(self.filterLetter): return False
		if self.filterRuntime and self.filterRuntime < i.runtime: return False
		if self.filterWatched != None and self.filterWatched != i.watched: return False
		return True
				
	def addSection(self,i):
		item = xbmcgui.ListItem()
		item.setProperty('paging','section')
		if i._section == 'THISWEEK':
			item.setLabel(T(32017))
		else:
			item.setLabel(T(32018))
		return item
	
	def setUpItem(self,item,i):
		item.setProperty('id',i.ID)
		item.setProperty('description',i.description)
		item.setProperty('info',i.info)
		item.setProperty('genre',i.genre)
		item.setProperty('rating',i.rating)
		item.setProperty('ratingImage',i.ratingImage)
		item.setProperty('url',i.url)
		item.setProperty('flag',i.flagImage)
		item.setProperty('catID',str(i.categoryID))
				
	def doMenu(self):
		if self.mode == 'COLLECTION':
			result = self.getCurrentItemResult()
			if not result: return
			m = ChoiceList(T(32028))
			m.addItem('remove',T(32029))
			if result.watched:
				m.addItem('unmarkwatched',T(32033))
			else:
				m.addItem('markwatched',T(32032))
				
			ID = m.getResult()
			if ID is None: return
			if ID == 'markwatched':
				self.toggleWatched(True)
			elif ID == 'unmarkwatched':
				self.toggleWatched(False)
			elif ID == 'remove':
				self.removeFromCollection()

		elif self.mode == 'PRICETRACKER':
			items = [T(32029),T(32030)]
			idx = xbmcgui.Dialog().select(T(32028),items)
			if idx < 0: return
			if idx == 0:
				self.unTrackPrice()
			elif idx == 1:
				self.editTrackPrice()
				
		elif self.mode == 'SEARCH':
			self.showReviews()

	def changeCategory(self):
		m = ChoiceSlideout(T(32028))
		m.addItem('all',T(32031))
		for cat_id, cat in self.getCollectionCategoriesToShow(): # @UnusedVariable
			m.addItem(cat_id,cat)
		ID = m.getResult()
		if ID is None: return
		if ID == 'all':
			self.refresh(category=0)
		else:
			self.refresh(category=ID)
				
	def getCurrentItemResult(self):
		results = filter(self.filter,self.currentResults)
		idx = self.reviewList.getSelectedPosition()
		if idx < self.idxOffset: return
		idx += self.idxOffset
		if idx > len(results): return
		result = results[idx]
		return result
			
	def openFilterWindow(self):
		w = openWindow(BluRayFilter,'bluray-com-filter.xml',return_window=True)
		if w.canceled: return
		self.filterLetter = w.letter
		self.filterGenre1 = w.genre1
		self.filterGenre2 = w.genre2
		self.filterGenre3 = w.genre3
		self.filterRuntime = w.time
		self.filterWatched = w.watched
		self.filterGenre1Exclude = w.genre1Exclude
		self.filterGenre2Exclude = w.genre2Exclude
		self.filterGenre3Exclude = w.genre3Exclude
		self.setFilterString()
		del w
		self.refresh(filterChange=True)
				
	def setFilterString(self):
		filters = []
		if self.filterLetter: filters.append(self.filterLetter)
		for ex, gid in ((self.filterGenre1Exclude,self.filterGenre1),(self.filterGenre2Exclude,self.filterGenre2),(self.filterGenre3Exclude,self.filterGenre3)):
			if gid:
				f = (ex and '-' or '') + bluraycomapi.getGenreByID(gid)
				filters.append(f)
		if self.filterRuntime: filters.append(bluraycomapi.minsToDuration(self.filterRuntime))
		if self.filterWatched != None: filters.append(self.filterWatched and 'Watched' or 'Unwatched')
		self.filterString = ' : '.join(filters)

	def unTrackPrice(self):
		self.loadingOn()
		succeeded = False
		try:
			result = self.getCurrentItemResult()
			if not result: return
			succeeded = API.unTrackPrice(result.itemID)
		finally:
			self.loadingOff()
			
		if succeeded:
			self.refresh()
			
	def editTrackPrice(self):
		self.loadingOn()
		try:
			result = self.getCurrentItemResult()
			if not result: return
			succeeded = trackPrice(result.trackingID,result.itemID,price=result.myPrice)
		finally:
			self.loadingOff()
			
		if succeeded:
			self.refresh()
	
	def toggleWatched(self,watched=None):
		self.loadingOn()
		succeeded = False
		try:
			result = self.getCurrentItemResult()
			if not result: return
			if watched is None:
				result.json['watched'] = result.json.get('watched') != '1' and '1' or ''
			else:
				result.json['watched'] = watched and '1' or ''
			succeeded = API.updateCollectable(result.json)
		finally:
			self.loadingOff()
			
		if succeeded:
			item = self.reviewList.getSelectedItem()
			result.refresh()
			self.setUpItem(item, result)
			self.setFocus(self.reviewList)
		
	def removeFromCollection(self):
		result = self.getCurrentItemResult()
		if not result: return
		yes = xbmcgui.Dialog().yesno('Really Delete?','Really remove:',result.title,'from your collection?')
		if not yes: return
		self.loadingOn()
		succeeded = False
		try:
			succeeded = API.deleteCollectable(result.ID)
		finally:
			self.loadingOff()
			
		if succeeded:
			self.refresh(category=self.lastCategory)

	def onClick(self,controlID):
		if controlID == 101:
			item = self.reviewList.getSelectedItem()
			if not item: return
			if item.getProperty('paging'):
				if item.getProperty('paging') == 'section': return
				self.refresh(page=item.getProperty('page'))
			else:
				openWindow(BluRayReview, 'bluray-com-review.xml',url=item.getProperty('url'),cat_id=item.getProperty('catID'))
				
	def onAction(self,action):
		try:
			if action == 117:
				self.doMenu()
			elif action == 9 or action == 10:
				self.doClose()
			elif action == 2:
				if self.mode == 'COLLECTION': self.openFilterWindow()
			elif action == 1:
				if self.mode == 'COLLECTION': self.changeCategory()
		finally:
			BaseWindowDialog.onAction(self,action)
	
class BluRayReview(BaseWindowDialog):
	def __init__(self,*args,**kwargs):
		BaseWindowDialog.__init__(self)
		self.url = kwargs.get('url')
		self.categoryID = kwargs.get('cat_id')
		self.review = None
		
	def onInit(self):
		BaseWindowDialog.onInit(self)
		self.imagesList = self.getControl(102)
		self.altList = self.getControl(134)
		self.reviewText = self.getControl(130)
		self.infoText = self.getControl(132)
		self.loading = self.getControl(149)
		self.showReview()
	
	def reset(self,link):
		self.url = link
		self.imagesList.reset()
		self.altList.reset()
		self.reviewText.reset()
		self.infoText.reset()
		self.showReview()
		
	def showReview(self):
		self.loading.setVisible(True)
		try:
			review = API.getReview(self.url,self.categoryID)
			self.review = review
			self.setProperty('title', review.title)
			self.setProperty('subheading1', review.subheading1)
			self.setProperty('subheading2', review.subheading2)
			self.setProperty('flag', review.flagImage)
			self.setProperty('cover', review.coverImage)
			self.setProperty('owned',review.owned and T(32019) or '')
			self.reviewText.setText(review.review)
			
			self.infoText.setText(('[CR][B]%s[/B][CR]' % ('_' * 200)).join(filter(bool,[review.price,review.blurayRating,review.overview,review.specifications])))
			
			items = []
			for ID,tn in review.imdbVideos:
				item = xbmcgui.ListItem(iconImage=tn)
				item.setProperty('video','1')
				item.setProperty('id',ID)
				items.append(item)
			for url,url_1080p in review.images:
				item = xbmcgui.ListItem(iconImage=url)
				item.setProperty('1080p',url_1080p)
				items.append(item)
			if review.coverFront or review.coverBack:
				item = xbmcgui.ListItem()
				item.setProperty('front',review.coverImage or 'script-bluray-com-no_cover.png')
				item.setProperty('frontLarge',review.coverFront or 'script-bluray-com-no_cover.png')
				item.setProperty('back',review.coverBack or 'script-bluray-com-no_cover.png')
				items.append(item)
			ct = 0
			for source, url in review.historyGraphs:  # @UnusedVariable
				url = imageToCache(url,'graph%s.png' % ct)
				item = xbmcgui.ListItem(iconImage=url)
				item.setProperty('1080p',url)
				items.append(item)
				ct += 1
			self.imagesList.addItems(items)
			
			items = []
			if review.otherEditions:
				item = xbmcgui.ListItem(label=T(32015))
				item.setProperty('separator','1')
				items.append(item)
				
			for link, image, text in review.otherEditions:
				item = xbmcgui.ListItem(iconImage=image)
				item.setProperty('link',link)
				item.setProperty('text',text)
				items.append(item)
				
			if review.similarTitles:
				item = xbmcgui.ListItem(label=T(32016))
				item.setProperty('separator','1')
				items.append(item)
				
			for link, image, text in review.similarTitles:
				item = xbmcgui.ListItem(iconImage=image)
				item.setProperty('link',link)
				item.setProperty('text',text)
				items.append(item)
			if items:
				self.setProperty('has_other', '1')
				self.altList.addItems(items)
		finally:
			self.loading.setVisible(False)
			self.setFocus(self.imagesList)
			self.setFocusId(200)
		
	def doMenu(self):
		items = [T(32027)]
		idx = xbmcgui.Dialog().select(T(32028),items)
		if idx < 0: return
		if idx == 0:
			trackPrice(API.getTrackingIDWithURL(self.review.url))
	
	def onClick(self,controlID):
		if controlID == 102:
			item = self.imagesList.getSelectedItem()
			if not item: return
			if item.getProperty('video'):
				bluraycomapi.playIMDBVideo(item.getProperty('id'))
			else:
				openWindow(ImageViewer, 'bluray-com-image.xml',url=item.getProperty('1080p'),front=item.getProperty('frontLarge'),back=item.getProperty('back'))
		elif controlID == 134:
			item = self.altList.getSelectedItem()
			if not item: return
			link = item.getProperty('link')
			if not link: return
			self.reset(link)
			
	def onAction(self,action):
		try:
			if xbmc.getCondVisibility('Player.Playing + Player.HasVideo'):
				pass
			elif action == 9 or action == 10:
				self.doClose()
			elif action == 117:
				self.doMenu()
		finally:
			BaseWindowDialog.onAction(self,action)
			
class BluRaySearch(BaseWindowDialog):
	def __init__(self,*args,**kwargs):
		self.keywords = LAST_SEARCH
		self.section = 'bluraymovies'
		self.country = 'all'
		self.canceled = True
		BaseWindowDialog.__init__(self)
		
	def onInit(self):
		BaseWindowDialog.onInit(self)
		self.keywordsButton = self.getControl(102)
		self.sectionList = self.getControl(100)
		self.countryList = self.getControl(101)
		self.fillSearch()
		
	def fillSearch(self):
		if LAST_SEARCH: self.keywordsButton.setLabel(LAST_SEARCH)
		lastSection = getSetting('search_last_section','')
		lastCountry = getSetting('search_last_country','')
		sectionIDX = 0
		countryIDX = 0
		
		items = []
		ct = 0
		for sid, sname, catID in API.sections:  # @UnusedVariable
			item = xbmcgui.ListItem(label=sname)
			item.setProperty('sectionid',sid)
			items.append(item)
			if sid == lastSection: sectionIDX = ct
			ct+=1
		self.sectionList.addItems(items)
		items = []
		ct = 0
		for c in API.countries:
			item = xbmcgui.ListItem(label=c.get('n',''))
			item.setProperty('flag',c.get('u',''))
			ccode = c.get('c','')
			item.setProperty('country',ccode)
			items.append(item)
			if ccode == lastCountry: countryIDX = ct 
			ct+=1
		self.countryList.addItems(items)
		
		self.sectionList.selectItem(sectionIDX)
		self.countryList.selectItem(countryIDX)
		
	def getKeywords(self):
		key = xbmc.Keyboard(LAST_SEARCH,T(32007))
		key.doModal()
		if not key.isConfirmed(): return
		terms = key.getText()
		if not terms: return
		del key
		self.keywords = terms
		self.keywordsButton.setLabel(terms)
				
	def setSearch(self):
		global LAST_SEARCH
		self.canceled = False
		self.section = self.sectionList.getSelectedItem().getProperty('sectionid')
		self.country = self.countryList.getSelectedItem().getProperty('country')
		if self.keywords: LAST_SEARCH = self.keywords
		ADDON.setSetting('search_last_section',self.section)
		ADDON.setSetting('search_last_country',self.country)
			
	def onClick(self,controlID):
		if controlID == 102:
			self.getKeywords()
		elif controlID == 103:
			self.setSearch()
			self.doClose()
			
	def onAction(self,action):
		try:
			if action == 9 or action == 10:
				self.doClose()
		finally:
			BaseWindowDialog.onAction(self,action)
			
class BluRayFilter(BaseWindowDialog):
	def __init__(self,*args,**kwargs):
		BaseWindowDialog.onInit(self)
		self.canceled = True
		self.letter = ''
		self.genre1 = ''
		self.genre2 = ''
		self.genre3 = ''
		self.time = ''
		self.watched = None
		self.genre1Exclude = getSetting('filter_last_excludegenre1',False)
		self.genre2Exclude = getSetting('filter_last_excludegenre2',False)
		self.genre3Exclude = getSetting('filter_last_excludegenre3',False)
		BaseWindowDialog.__init__(self)
		
	def onInit(self):
		BaseWindowDialog.onInit(self)
		self.letterList = self.getControl(100)
		self.genre1List = self.getControl(101)
		self.genre2List = self.getControl(104)
		self.genre3List = self.getControl(107)
		self.timeList = self.getControl(105)
		self.wathcedList = self.getControl(106)
		self.setup()
		
	def setup(self):
		self.setProperty('excludegenre1',self.genre1Exclude and '1' or '')
		self.setProperty('excludegenre2',self.genre2Exclude and '1' or '')
		self.setProperty('excludegenre3',self.genre3Exclude and '1' or '')
		
		lastLetter = getSetting('filter_last_letter','')
		lastGenre1 = getSetting('filter_last_genre1','')
		lastGenre2 = getSetting('filter_last_genre2','')
		lastGenre3 = getSetting('filter_last_genre3','')
		lastTime = getSetting('filter_last_time',0)
		lastWatched = getSetting('filter_last_watched','')
		letterIDX = 0
		genre1IDX = 0
		genre2IDX = 0
		genre3IDX = 0
		timeIDX = 0
		watchedIDX = 0
		
		items = []
		ct=0
		letters = ('','A','B','C','D','E','F','G','H','I','J','K','L','M','N','O','P','Q','R','S','T','U','V','U','W','X','Y','Z')
		for letter in letters:
			item = xbmcgui.ListItem(label=letter or '-')
			item.setProperty('letter',letter)
			items.append(item)
			if lastLetter == letter: letterIDX = ct
			ct+=1
		self.letterList.addItems(items)
		
		items = []
		ct = 0
		for name,label,ID in API.genres:
			item = xbmcgui.ListItem(label=label)
			item.setProperty('id',ID)
			item.setProperty('name',name)
			items.append(item)
			if ID == lastGenre1: genre1IDX = ct 
			ct+=1
		self.genre1List.addItems(items)
		
		items = []
		ct = 0
		for name,label,ID in API.genres:
			item = xbmcgui.ListItem(label=label)
			item.setProperty('id',ID)
			item.setProperty('name',name)
			items.append(item)
			if ID == lastGenre2: genre2IDX = ct 
			ct+=1
		self.genre2List.addItems(items)
		
		items = []
		ct = 0
		for name,label,ID in API.genres:
			item = xbmcgui.ListItem(label=label)
			item.setProperty('id',ID)
			item.setProperty('name',name)
			items.append(item)
			if ID == lastGenre3: genre3IDX = ct 
			ct+=1
		self.genre3List.addItems(items)
		
		times = ((0,'-'),(30,'30 mins'),(45,'45 mins'),(60,'1 hr'),(75,u'1\xbc hrs'),(90,u'1\xbd hrs'),(120,'2 hrs'),(150,u'2\xbd hrs'),(180,'3 hrs'))
		items = []
		ct = 0
		for mins,label in times:
			item = xbmcgui.ListItem(label=label)
			item.setProperty('runtume',str(mins))
			items.append(item)
			if mins == lastTime: timeIDX = ct 
			ct+=1
		self.timeList.addItems(items)
		
		wlist = (('','-'),('0','Unwatched'),('1','Watched'))
		items = []
		ct = 0
		for watched,label in wlist:
			item = xbmcgui.ListItem(label=label)
			item.setProperty('watched',watched)
			items.append(item)
			if watched == lastWatched: watchedIDX = ct 
			ct+=1
		self.wathcedList.addItems(items)
		
		self.letterList.selectItem(letterIDX)
		self.genre1List.selectItem(genre1IDX)
		self.genre2List.selectItem(genre2IDX)
		self.genre3List.selectItem(genre3IDX)
		self.timeList.selectItem(timeIDX)
		self.wathcedList.selectItem(watchedIDX)
				
	def setFilter(self):
		self.canceled = False
		self.letter = self.letterList.getSelectedItem().getProperty('letter')
		self.genre1 = self.genre1List.getSelectedItem().getProperty('id')
		self.genre2 = self.genre2List.getSelectedItem().getProperty('id')
		self.genre3 = self.genre3List.getSelectedItem().getProperty('id')
		self.time = int(self.timeList.getSelectedItem().getProperty('runtume'))
		watched = self.wathcedList.getSelectedItem().getProperty('watched')
		if not watched:
			self.watched = None
		else:
			self.watched = watched == '1' 
		ADDON.setSetting('filter_last_letter',self.letter)
		ADDON.setSetting('filter_last_genre1',self.genre1)
		ADDON.setSetting('filter_last_genre2',self.genre2)
		ADDON.setSetting('filter_last_genre3',self.genre3)
		ADDON.setSetting('filter_last_time',str(self.time))
		ADDON.setSetting('filter_last_watched',watched)
		ADDON.setSetting('filter_last_excludegenre1',str(self.genre1Exclude).lower())
		ADDON.setSetting('filter_last_excludegenre2',str(self.genre2Exclude).lower())
		ADDON.setSetting('filter_last_excludegenre3',str(self.genre3Exclude).lower())
			
	def onClick(self,controlID):
		if controlID == 103:
			self.setFilter()
			self.doClose()
		elif controlID == 101:
			if self.genre1Exclude:
				self.genre1Exclude = False
				self.setProperty('excludegenre1','')
			else:
				self.genre1Exclude = True
				self.setProperty('excludegenre1','1')
		elif controlID == 104:
			if self.genre2Exclude:
				self.genre2Exclude = False
				self.setProperty('excludegenre2','')
			else:
				self.genre2Exclude = True
				self.setProperty('excludegenre2','1')
		elif controlID == 107:
			if self.genre3Exclude:
				self.genre3Exclude = False
				self.setProperty('excludegenre3','')
			else:
				self.genre3Exclude = True
				self.setProperty('excludegenre3','1')
			
	def onAction(self,action):
		try:
			if action == 9 or action == 10:
				self.doClose()
		finally:
			BaseWindowDialog.onAction(self,action)
			
class BluRaySelect(BaseWindowDialog):
	def __init__(self,*args,**kwargs):
		self.selection = None
		self.canceled = True
		self.items = kwargs.get('items')
		BaseWindowDialog.__init__(self)
		
	def onInit(self):
		BaseWindowDialog.onInit(self)
		self.itemList = self.getControl(100)
		self.fillItems()
		
	def fillItems(self):
		
		items = []
		for label in self.items:  # @UnusedVariable
			item = xbmcgui.ListItem(label=label)
			items.append(item)
		self.itemList.addItems(items)
				
	def setSelection(self):
		self.canceled = False
		self.selection = self.itemList.getSelectedPosition()
		if self.selection < 0: self.selection = None
			
	def onClick(self,controlID):
		if controlID == 100:
			self.setSelection()
			self.doClose()
			
	def onAction(self,action):
		try:
			if action == 9 or action == 10:
				self.doClose()
			elif action == 2 or action == 1:
				self.doClose()
		finally:
			BaseWindowDialog.onAction(self,action)
			
class ImageViewer(BaseWindowDialog):
	def __init__(self,*args,**kwargs):
		BaseWindowDialog.__init__(self)
		self.url = kwargs.get('url','')
		self.front = kwargs.get('front','')
		self.back = kwargs.get('back','')
		
	def onInit(self):
		BaseWindowDialog.onInit(self)
		self.setProperty('image',self.url)
		self.setProperty('front',self.front)
		self.setProperty('back',self.back)
		
		self.setProperty('show_images','1')
		
	def onAction(self,action):
		try:
			if action == 9 or action == 10:
				self.close()
		finally:
			xbmcgui.WindowXMLDialog.onAction(self,action)

class ChoiceList:
	def __init__(self,caption=''):
		self.caption = caption
		self.items = []
		
	def addItem(self,ID,label):
		self.items.append({'id':ID,'label':label})
		
	def addSep(self):
		self.items.append({'id':None,'label':' '})
		
	def getResult(self):
		items = []
		for i in self.items: items.append(i['label'])
		idx = xbmcgui.Dialog().select(self.caption,items)
		if idx < 0: return None
		return self.items[idx]['id']
		
class ChoiceSlideout(ChoiceList):
	def getResult(self):
		items = []
		for i in self.items: items.append(i['label'])
		w = openWindow(BluRaySelect,'bluray-com-select.xml',return_window=True,items=items)
		idx = w.selection
		del w
		if idx == None: return
		return self.items[idx]['id']

def doKeyboard(heading,default='',hidden=False):
	key = xbmc.Keyboard(default,heading,hidden)
	key.doModal()
	if not key.isConfirmed(): return None
	return key.getText()

def trackPrice(product_id,update_id=None,price='19.99'):
	if not product_id:
		LOG('trackPrice(): No product ID')
		return
	while price != None:
		price = doKeyboard('Enter Price',str(price))
		try:
			float(price)
			if not '.' in price: raise Exception()
			break
		except:
			pass
	if not price: return
	price_range = '0'
	expiration = '8'
	return API.trackPrice(product_id, price, price_range, expiration,update_id)

def getSetting(key,default=None):
	setting = ADDON.getSetting(key)
	return _processSetting(setting,default)

def _processSetting(setting,default):
	if not setting: return default
	if isinstance(default,bool):
		return setting.lower() == 'true'
	elif isinstance(default,int):
		return int(float(setting or 0))
	elif isinstance(default,list):
		if setting: return setting.split(':!,!:')
		else: return default
	
	return setting

def updateUserPass():
	API.user = ADDON.getSetting('user') or None
	API.md5password = ADDON.getSetting('pass') or None
	
def getPassword():
	key = xbmc.Keyboard('',T(32026),True)
	key.doModal()
	if not key.isConfirmed(): return
	password = key.getText()
	if not password: return
	del key
	import hashlib
	ADDON.setSetting('pass',hashlib.md5(password).hexdigest())
	
def setGlobalSkinProperty(key,value=''):
	xbmcgui.Window(10000).setProperty('script.bluray.com-%s' % key,value)
	
def openReviewsWindow(mode=None):
	setGlobalSkinProperty('reviews_open','1')
	openWindow(BluRayReviews,'bluray-com-reviews.xml',mode=mode)
	setGlobalSkinProperty('reviews_open','0')
		
def openWindow(window_class,xml_file,return_window=False,**kwargs):
	w = window_class(xml_file , xbmc.translatePath(ADDON.getAddonInfo('path')), 'Main',**kwargs)
	w.doModal()
	if return_window:
		return w
	else:
		del w
	
def main():
	global API
	bluraycomapi.TR.update({	'reviews':T(32001),
								'releases':T(32002),
								'deals':T(32003),
								'search':T(32004),
								'collection':T(32010),
								'watched':T(32011),
								'yes':T(32012)
							})
	API = bluraycomapi.BlurayComAPI()
	updateUserPass()
	openWindow(BluRayCategories,'bluray-com-categories.xml')
	
if __name__ == '__main__':
	if sys.argv[-1] == 'get_password':
		getPassword()
	else:
		main()

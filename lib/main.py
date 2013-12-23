import os, shutil, requests
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
		
	def loadingOn(self):
		if not self.loading: return
		self.setProperty('loading','1')
		
	def loadingOff(self):
		if not self.loading: return
		self.setProperty('loading','0')
		
	def setProperty(self,key,value):
		xbmcgui.Window(xbmcgui.getCurrentWindowDialogId()).setProperty(key,value)
		xbmcgui.WindowXMLDialog.setProperty(self,key,value)
	
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
			elif item.getProperty('id') == 'search':
				global LAST_SEARCH
				key = xbmc.Keyboard(LAST_SEARCH,T(32007))
				key.doModal()
				if not key.isConfirmed(): return
				terms = key.getText()
				if not terms: return
				LAST_SEARCH = terms
				del key
				openReviewsWindow(search=terms)
				
class BluRayReviews(BaseWindowDialog):
	def __init__(self,*args,**kwargs):
		BaseWindowDialog.__init__(self)
		self.search = kwargs.get('search')
		self.mode = kwargs.get('mode')
		self.currentResults = []
		self.idxOffset = 0
	
	def onInit(self):
		self.reviewList = self.getControl(101)
		self.loading = self.getControl(149)
		self.showReviews()
	
	def refresh(self,page=0,category=7):
		self.reviewList.reset()
		self.showReviews(page=page,category=category)
		
	def showReviews(self,page=0,category=7):
		self.loadingOn()
		try:
			paging = (None,None)
			if self.search:
				results = API.search(self.search)
				if not results:
					xbmcgui.Dialog().ok(T(32008),T(32009))
					self.close()
					return
			elif self.mode == 'RELEASES':
				results = API.getReleases()
			elif self.mode == 'DEALS':
				results, paging = API.getDeals(page)
			elif self.mode == 'COLLECTION':
				results = API.getCollection(category=category)
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

	def addSection(self,i):
		item = xbmcgui.ListItem()
		item.setProperty('paging','section')
		if i._section == 'THISWEEK':
			item.setLabel("This Week")
		else:
			item.setLabel("Next Week")
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
				
	def doMenu(self):
		if self.mode == 'COLLECTION':
			items = ['Blu-ray','DVD','Toggle Watched']
			idx = xbmcgui.Dialog().select('Category',items)
			if idx < 0: return
			if idx == 0:
				self.refresh(category=7)
			elif idx == 1:
				self.refresh(category=21)
			elif idx == len(items) - 1:
				self.toggleWatched()

	def toggleWatched(self):
		self.loadingOn()
		succeeded = False
		try:
			idx = self.reviewList.getSelectedPosition()
			if idx < self.idxOffset: return
			idx += self.idxOffset
			if idx > len(self.currentResults): return
			result = self.currentResults[idx]
			result.json['watched'] = result.json.get('watched') != '1' and '1' or ''
			succeeded = API.updateCollectable(result.json)
		finally:
			self.loadingOff()
			
		if succeeded:
			item = self.reviewList.getSelectedItem()
			result.refresh()
			self.setUpItem(item, result)
			self.setFocus(self.reviewList)
		
	def onClick(self,controlID):
		if controlID == 101:
			item = self.reviewList.getSelectedItem()
			if not item: return
			if item.getProperty('paging'):
				if item.getProperty('paging') == 'section': return
				self.refresh(page=item.getProperty('page'))
			else:
				openWindow(BluRayReview, 'bluray-com-review.xml',url=item.getProperty('url'))
				
	def onAction(self,action):
		try:
			if action == 117:
				self.doMenu()
		finally:
			xbmcgui.WindowXMLDialog.onAction(self,action)
	
class BluRayReview(BaseWindowDialog):
	def __init__(self,*args,**kwargs):
		BaseWindowDialog.__init__(self)
		self.url = kwargs.get('url')
		
	def onInit(self):
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
			review = API.getReview(self.url)
			self.setProperty('title', review.title)
			self.setProperty('subheading1', review.subheading1)
			self.setProperty('subheading2', review.subheading2)
			self.setProperty('flag', review.flagImage)
			self.setProperty('cover', review.coverImage)
			self.reviewText.setText(review.review)
			
			self.infoText.setText(('[CR][B]%s[/B][CR]' % ('_' * 200)).join((review.price,review.blurayRating,review.overview,review.specifications)))
			
			items = []
			for url,url_1080p in review.images:
				item = xbmcgui.ListItem(iconImage=url)
				item.setProperty('1080p',url_1080p)
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
			self.altList.addItems(items)
			self.setFocus(self.imagesList)
		finally:
			self.loading.setVisible(False)
		
	def onClick(self,controlID):
		if controlID == 102:
			item = self.imagesList.getSelectedItem()
			if not item: return
			openWindow(ImageViewer, 'bluray-com-image.xml',url=item.getProperty('1080p'))
		elif controlID == 134:
			item = self.altList.getSelectedItem()
			if not item: return
			link = item.getProperty('link')
			if not link: return
			self.reset(link)
			

class ImageViewer(xbmcgui.WindowXMLDialog):
	def __init__(self,*args,**kwargs):
		self.url = kwargs.get('url')
		xbmcgui.WindowXML.__init__(self)
		
	def onInit(self):
		self.getControl(150).setImage(self.url)

def updateUserPass():
	API.user = ADDON.getSetting('user') or None
	API.password = ADDON.getSetting('pass') or None
		
def setGlobalSkinProperty(key,value=''):
	xbmcgui.Window(10000).setProperty('script.bluray.com-%s' % key,value)
	
def openReviewsWindow(search=None,mode=None):
	setGlobalSkinProperty('reviews_open','1')
	openWindow(BluRayReviews,'bluray-com-reviews.xml',search=search,mode=mode)
	setGlobalSkinProperty('reviews_open','0')
		
def openWindow(window_class,xml_file,**kwargs):
	w = window_class(xml_file , xbmc.translatePath(ADDON.getAddonInfo('path')), 'Main',**kwargs)
	w.doModal()
	del w
	
def main():
	global API
	bluraycomapi.TR = {	'reviews':T(32001),
						'releases':T(32002),
						'deals':T(32003),
						'search':T(32004),
						'collection':T(32010),
						'watched':T(32011),
						'yes':T(32012)
	}
	API = bluraycomapi.BlurayComAPI()
	updateUserPass()
	openWindow(BluRayCategories,'bluray-com-categories.xml')
	
if __name__ == '__main__':
	main()

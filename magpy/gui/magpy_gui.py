#!/usr/bin/env python

from __future__ import print_function
import wx

from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigureCanvas
from matplotlib.backends.backend_wx import NavigationToolbar2Wx
from matplotlib.figure import Figure

try: # Necessary for wx2.8.11.0
    from wx.lib.pubsub import setupkwargs
    # later versions: wxPython-phoenix
    # sudo pip3 install -U --pre -f http://wxpython.org/Phoenix/snapshot-builds/ wxPython_Phoenix
    # does not work so far! leon 2016-06-24
except:
    pass
from wx.lib.pubsub import pub

from magpy.stream import read
import magpy.mpplot as mp
#import magpy.absolutes import as di
from magpy.absolutes import *
from magpy.transfer import *
from magpy.database import *
from magpy.version import __version__
from magpy.gui.streampage import *
from magpy.gui.metapage import *
from magpy.gui.dialogclasses import *
from magpy.gui.absolutespage import *
from magpy.gui.reportpage import *
from magpy.gui.developpage import *  # remove this
from magpy.gui.analysispage import *
from magpy.gui.monitorpage import *
#try:
#    from magpy.collector import subscribe2client as msubs
#except:
#    print ("MARTAS and LogFile options not available - check dependencies")
import glob, os, pickle, base64
import pylab
import thread, time
import threading


def saveobj(obj, filename):
    with open(filename, 'wb') as f:
        pickle.dump(obj,f,pickle.HIGHEST_PROTOCOL)

def loadobj(filename):
    with open(filename, 'rb') as f:
        return pickle.load(f)

def pydate2wxdate(datum):
     assert isinstance(datum, (datetime, datetime.date))
     tt = datum.timetuple()
     dmy = (tt[2], tt[1]-1, tt[0])
     print (tt, dmy)
     return wx.DateTimeFromDMY(*dmy)
 
def wxdate2pydate(date):
     assert isinstance(date, wx.DateTime)
     if date.IsValid():
          ymd = map(int, date.FormatISODate().split('-'))
          return datetime.date(*ymd)
     else:
          return None

def saveini(dbname=None, user=None, passwd=None, host=None, dirname=None, compselect=None, abscompselect=None, basecompselect=None, resolution=None, dipathlist = None, divariopath = None, discalarpath = None, diexpD = None, diexpI = None, stationid = None, diid = None, ditype = None, diazimuth = None, dipier = None, dialpha = None, dideltaF = None, didbadd = None, bookmarks = None):
    """
    Method for creating credentials
    """

    if not dbname:
        dbname = 'None'
    if not user:
        user = 'max'
    if not passwd:
        passwd = 'secret'
    if not host:
        host = 'localhost'
    if not dirname:
        dirname = '/srv'
    if not basecompselect:
        basecompselect = 'bspline'

    if not dipathlist:
        dipathlist = ''
    if not divariopath:
        divariopath = ''
    if not discalarpath:
        discalarpath = ''
    if not diexpD:
        diexpD = 3.0
    if not diexpI:
        diexpI = 64.0
    if not stationid:
        stationid = 'wic'
    if not diid:
        diid = ''
    if not ditype:
        ditype = 'DI' #abstype = ''
    if not diazimuth:
        diazimuth = ''
    if not dipier:
        dipier = 'A2'
    if not dialpha:
        dialpha = '0.0'
    if not dideltaF:
        dideltaF = '2.1'
    if not didbadd:
        didbadd = 'False'
    if not bookmarks:
        bookmarks = ['http://www.intermagnet.org/test/ws/?id=BOU','ftp://ftp.nmh.ac.uk/wdc/obsdata/hourval/single_year/2011/fur2011.wdc','ftp://user:passwd@www.zamg.ac.at//data/magnetism/wic/variation/WIC20160627pmin.min']
    # starttime,endtime
    #if not db=db # test whether db is connected

    home = os.path.expanduser('~')
    initpath = os.path.join(home,'.magpyguiini')

    pwd = base64.b64encode(passwd)

    dictionary = {'dbname': dbname, 'user':user, 'passwd':pwd, 'host':host, \
                  'dirname':dirname, \
                  'basecompselect':basecompselect, 'resolution':resolution, 'dipathlist':dipathlist, 'divariopath':divariopath, 'discalarpath':discalarpath, 'diexpD':diexpD, 'diexpI':diexpI, 'stationid':stationid, 'diid':diid, 'ditype':ditype, 'diazimuth':diazimuth, 'dipier':dipier, 'dialpha':dialpha, 'dideltaF':dideltaF, 'didbadd':didbadd , 'bookmarks':bookmarks}

    saveobj(dictionary, initpath)
    print ("Initialization: Added data ")


def loadini():
    """
    Load initialisation data

    """
    home = os.path.expanduser('~')
    initpath = os.path.join(home,'.magpyguiini')
    print ("Trying to access initialization file:", initpath)

    try:
        initdata = loadobj(initpath)
        print ("... success")
    except:
        print ("Init file not found: Could not load data")
        return False

    #print "Initialization data loaded"
    return initdata


class RedirectText(object):
    # Taken from: http://www.blog.pythonlibrary.org/2009/01/01/wxpython-redirecting-stdout-stderr/
    # Used to redirect di results to the multiline textctrl on the DI page
    def __init__(self,aWxTextCtrl):
        self.out=aWxTextCtrl

    def write(self,string):
        self.out.WriteText(string)

class PlotPanel(wx.Panel):
    """
    DESCRIPTION
        comtains all methods for the left plot panel
    """
    def __init__(self, *args, **kwds):
        wx.Panel.__init__(self, *args, **kwds)
        self.figure = plt.figure()
        self.plt = plt
        scsetmp = ScreenSelections()
        self.canvas = FigureCanvas(self,-1,self.figure)
        self.datavars = {} # for monitoring
        self.array = [[] for key in KEYLIST] # for monitoring
        self.t1_stop= threading.Event()
        self.xlimits = None
        self.initialPlot()
        self.__do_layout()

    def __do_layout(self):
        # Resize graph and toolbar, create toolbar
        self.vbox = wx.BoxSizer(wx.VERTICAL)
        self.vbox.Add(self.canvas, 1, wx.LEFT | wx.TOP | wx.GROW)
        self.toolbar = NavigationToolbar2Wx(self.canvas)
        self.vbox.Add(self.toolbar, 0, wx.EXPAND)
        self.SetSizer(self.vbox)
        self.vbox.Fit(self)


    def timer(self, arg1, stop_event):
        while(not stop_event.is_set()):
            self.update(self.array)
            print ("Running ...")
            stop_event.wait(self.datavars[7])
            pass


    def update(self,array):
        """
        DESCRIPTION
            Update array with new data and plot it.
            If log file is chosen the this method makes use of collector.subscribe method:
            storeData to save binary file
        """
        def list_duplicates(seq):
            seen = set()
            seen_add = seen.add
            return [idx for idx,item in enumerate(seq) if item in seen or seen_add(item)]

        db = self.datavars[8]
        parameterstring = 'time,'+self.datavars[1]
        # li should contain a data source of a certain length (can be filled by any reading process)
        li = sorted(dbselect(db, parameterstring, self.datavars[0], expert='ORDER BY time DESC LIMIT {}'.format(int(self.datavars[2]))))
        tmpdt = [datetime.strptime(elem[0], "%Y-%m-%d %H:%M:%S.%f") for elem in li]
        self.array[0].extend(tmpdt)
        for idx,para in enumerate(parameterstring.split(',')):
            if not para.endswith('time'):
                i = KEYLIST.index(para)
                self.array[i].extend([float(elem[idx]) for elem in li])

        duplicateindicies = list_duplicates(self.array[0])
        array = [[] for key in KEYLIST]
        for idx, elem in enumerate(self.array):
            if len(elem) > 0:
                newelem = np.delete(np.asarray(elem), duplicateindicies)
                array[idx] = list(newelem)

        coverage = int(self.datavars[6])

        array = [ar[-coverage:] if len(ar) > coverage else ar for ar in array ]

        self.monitorPlot(array)

        #if Log2File:
        #    msubs.output = 'file'
        #    #sensorid = row[0]
        #    #module = row[1]
        #    #line = row[2]
        #    #msubs.storeData(li,parameterstring.split(','))



    def startMARCOSMonitor(self,**kwargs):
        """
        DEFINITION:
            embbed matplotlib figure in canvas for mointoring

        PARAMETERS:
            kwargs:  - all plot args
        """

        dataid = self.datavars[0]
        parameter = self.datavars[1]
        period = self.datavars[2]
        pad = self.datavars[3]
        currentdate = self.datavars[4]
        unitlist = self.datavars[5]
        coverage = self.datavars[6]  # coverage
        updatetime = self.datavars[7]
        db = self.datavars[8]

        # convert parameter list to a dbselect sql format
        parameterstring = 'time,'+parameter

        # Test whether data is available at all with selected keys and dataid
        li = sorted(dbselect(db, parameterstring, dataid, expert='ORDER BY time DESC LIMIT {}'.format(int(coverage))))

        if not len(li) > 0:
            print("Did not find any data to display - aborting")
            return
        else:
            valkeys = ['time']
            valkeys = parameterstring.split(',')
            for i,elem in enumerate(valkeys):
                idx = KEYLIST.index(elem)
                if elem == 'time':
                    self.array[idx] = [datetime.strptime(el[0],"%Y-%m-%d %H:%M:%S.%f") for el in li]
                else:
                    self.array[idx] = [float(el[i]) for el in li]

        self.datavars = {0: dataid, 1: parameter, 2: period, 3: pad, 4: currentdate, 5: unitlist, 6: coverage, 7: updatetime, 8: db}

        self.figure.clear()
        t1 = threading.Thread(target=self.timer, args=(1,self.t1_stop))
        t1.start()
        # Display the plot
        self.canvas.draw()

    def monitorPlot(self,array,**kwargs):
        """
        DEFINITION:
            embbed matplotlib figure in canvas for mointoring

        PARAMETERS:
            kwargs:  - all plot args
        """

        # Read persistent data variables
        dataid = self.datavars[0]
        parameter = self.datavars[1]
        period = self.datavars[2]
        pad = self.datavars[3]
        currentdate = self.datavars[4]
        unitlist = self.datavars[5]
        coverage = self.datavars[6]  # coverage
        updatetime = self.datavars[7]
        db = self.datavars[8]

        # convert parameter list to a dbselect sql format
        parameterstring = 'time,'+parameter

        self.figure.clear()
        try:
            self.axes.clear()
        except:
            pass
        dt = array[0]
        self.figure.suptitle("Live Data of %s - %s" % (dataid, currentdate))
        for idx,para in enumerate(parameterstring.split(',')):
            if not para.endswith('time'):
                i = KEYLIST.index(para)
                subind = int("{}1{}".format(len(parameterstring.split(','))-1,idx))
                #print subind
                self.axes = self.figure.add_subplot(subind)
                self.axes.grid(True)
                rd = array[i]
                l, = self.axes.plot_date(dt,rd,'b-')
                #l, = a.plot_date(dt,td,'g-')
                plt.xlabel("Time")
                plt.ylabel(r'%s [%s]' % (unitlist[idx-1][0],unitlist[idx-1][1]))

                # Get the minimum and maximum temperatures these are
                # used for annotations and scaling the plot of data
                min_val = np.min(rd)
                max_val = np.max(rd)
   
                # Add annotations for minimum and maximum temperatures
                self.axes.annotate(r'Min: %0.1f' % (min_val),
                    xy=(dt[rd.index(min_val)], min_val),
                    xycoords='data', xytext=(20, -20),
                    textcoords='offset points',
                    bbox=dict(boxstyle="round", fc="0.8"),
                    arrowprops=dict(arrowstyle="->",
                    shrinkA=0, shrinkB=1,
                    connectionstyle="angle,angleA=0,angleB=90,rad=10"))

                self.axes.annotate(r'Max: %0.1f' % (max_val),
                    xy=(dt[rd.index(max_val)], max_val),
                    xycoords='data', xytext=(20, 20),
                    textcoords='offset points',
                    bbox=dict(boxstyle="round", fc="0.8"),
                    arrowprops=dict(arrowstyle="->",
                    shrinkA=0, shrinkB=1,
                    connectionstyle="angle,angleA=0,angleB=90,rad=10"))

        # Set the axis limits to make the data more readable
        #self.axes.axis([0,len(temps), min_t - pad,max_t + pad])
   
        self.figure.canvas.draw_idle()
   
        # Repack variables that need to be persistent between
        # executions of this method
        self.datavars = {0: dataid, 1: parameter, 2: period, 3: pad, 4: currentdate, 5: unitlist, 6: coverage, 7: updatetime, 8: db}


    def guiPlot(self,stream,keys,plotopt=None,**kwargs):
        """
        DEFINITION:
            embbed matplotlib figure in canvas

        PARAMETERS:
        kwargs:  - all plot args
        """
        #plotopt = {'labels':'None' , 'padding': 'None', 'stormphases': 'False', 'specialdict': 'None', 'bartrange':'None', 'bgcolor': 'white', 'colorlist': ",".join(collist[:lenkeys]) ,'fullday':'False', 'grid':'True','gridcolor':'#316931', 'includeid':'False', 'labelcolor':'0.2', 'legendposition':'upper left', 'plottitle':'', 'plottype':'discontinuous', 'symbollist':",".join(self.symbollist),'t_stormphases':'None', 'opacity':'0.0'}

        # Declare and register callbacks
        def on_xlims_change(axes):
            self.xlimits = axes.get_xlim()

        def on_ylims_change(axes):
            print ("updated ylims: ", axes.get_ylim())
            return axes.get_ylim()

        self.figure.clear()
        try:
            self.axes.clear()
        except:
            pass

        self.axes = mp.plot(stream,keys,figure=self.figure,**kwargs)
        self.axlist = self.figure.axes

        #get current xlimits:
        for ax in self.axlist:
            ax.callbacks.connect('xlim_changed', on_xlims_change)

        if not len(stream.ndarray[0])>0:
            t = [elem.time for elem in stream]
            flag = [elem.flag for elem in stream]
            k = [eval("elem."+keys[0]) for elem in stream]
        else:
            t = stream.ndarray[0]
            flagpos = KEYLIST.index('flag')
            firstcol = KEYLIST.index(keys[0])
            flag = stream.ndarray[flagpos]
            k = stream.ndarray[firstcol]
        #self.axes.af2 = self.AnnoteFinder(t,yplt,flag,self.axes)
        #self.axes.af2 = self.AnnoteFinder(t,k,flag,self.axes)
        #af2 = self.AnnoteFinder(t,k,flag,self.axes)
        #self.figure.canvas.mpl_connect('button_press_event', af2)

        self.canvas.draw()

    def initialPlot(self):
        """
        DEFINITION:
            loads an image for the startup screen
        """
        try:
            self.axes = self.figure.add_subplot(111)
            plt.axis("off") # turn off axis
            startupimage = 'magpy.png'
            # TODO add alternative positions
            # either use a walk to locate the image in /usr for linux and installation path on win
            # or put installation path in ini
            img = imread(startupimage)
            self.axes.imshow(img)
            self.canvas.draw()
        except:
            pass

    def linkRep(self):
        return ReportPage(self)

    class AnnoteFinder:
        """
        callback for matplotlib to display an annotation when points are clicked on.  The
        point which is closest to the click and within xtol and ytol is identified.

        Register this function like this:

        scatter(xdata, ydata)
        af = AnnoteFinder(xdata, ydata, annotes)
        connect('button_press_event', af)
        """

        def __init__(self, xdata, ydata, annotes, axis=None, xtol=None, ytol=None):
            self.data = zip(xdata, ydata, annotes)
            if xtol is None:
                xtol = ((max(xdata) - min(xdata))/float(len(xdata)))/2
            if ytol is None:
                ytol = ((max(ydata) - min(ydata))/float(len(ydata)))/2
            ymin = min(ydata)
            ymax = max(ydata)
            self.xtol = xtol
            self.ytol = ytol
            if axis is None:
                self.axis = pylab.gca()
            else:
                self.axis= axis
            self.drawnAnnotations = {}
            self.links = []

        def distance(self, x1, x2, y1, y2):
            """
            return the distance between two points
            """
            return math.hypot(x1 - x2, y1 - y2)

        def __call__(self, event):
            if event.inaxes:
                clickX = event.xdata
                clickY = event.ydata
                if self.axis is None or self.axis==event.inaxes:
                    annotes = []
                    for x,y,a in self.data:
                        #if  clickX-self.xtol < x < clickX+self.xtol and clickY-self.ytol < y < clickY+self.ytol:
                        if  clickX-self.xtol < x < clickX+self.xtol :
                            annotes.append((self.distance(x,clickX,y,clickY),x,y, a) )
                    if annotes:
                        annotes.sort()
                        distance, x, y, annote = annotes[0]
                        self.drawAnnote(event.inaxes, x, y, annote)
                        for l in self.links:
                            l.drawSpecificAnnote(annote)

        def drawAnnote(self, axis, x, y, annote):
            """
            Draw the annotation on the plot
            """
            if (x,y) in self.drawnAnnotations:
                markers = self.drawnAnnotations[(x,y)]
                for m in markers:
                    m.set_visible(not m.get_visible())
                self.axis.figure.canvas.draw()
            else:
                #t = axis.text(x,y, "(%3.2f, %3.2f) - %s"%(x,y,annote), )
                datum = datetime.strftime(num2date(x).replace(tzinfo=None),"%Y-%m-%d")
                t = axis.text(x,y, "(%s, %3.2f)"%(datum,y), )
                m = axis.scatter([x],[y], marker='d', c='r', zorder=100)
                scse = ScreenSelections()
                scse.seldatelist.append(x)
                scse.selvallist.append(y)
                scse.updateList()
                #test = MainFrame(parent=None)
                #test.ReportPage.addMsg(str(x))
                #rep_page.logMsg('Datum is %s ' % (datum))
                #l = axis.plot([x,x],[0,y])
                self.drawnAnnotations[(x,y)] =(t,m)
                self.axis.figure.canvas.draw()

        def drawSpecificAnnote(self, annote):
            annotesToDraw = [(x,y,a) for x,y,a in self.data if a==annote]
            for x,y,a in annotesToDraw:
                self.drawAnnote(self.axis, x, y, a)


class MenuPanel(wx.Panel):
    """
    DESCRIPTION
        comtains all methods for the right menu panel and their insets
        All methods are listed in the MainFrame class
    """
    def __init__(self, *args, **kwds):
        wx.Panel.__init__(self, *args, **kwds)
        # Create pages on MenuPanel
        nb = wx.Notebook(self,-1)
        self.str_page = StreamPage(nb)
        self.met_page = MetaPage(nb)
        self.ana_page = AnalysisPage(nb)
        self.abs_page = AbsolutePage(nb)
        self.rep_page = ReportPage(nb)
        self.com_page = MonitorPage(nb)
        nb.AddPage(self.str_page, "Stream")
        nb.AddPage(self.met_page, "Meta")
        nb.AddPage(self.ana_page, "Analysis")
        nb.AddPage(self.abs_page, "DI")
        nb.AddPage(self.rep_page, "Report")
        nb.AddPage(self.com_page, "Monitor")

        sizer = wx.BoxSizer()
        sizer.Add(nb, 1, wx.EXPAND)
        self.SetSizer(sizer)


class MainFrame(wx.Frame):
    def __init__(self, *args, **kwds):
        kwds["style"] = wx.DEFAULT_FRAME_STYLE
        wx.Frame.__init__(self, *args, **kwds)
        # The Splitted Window
        self.sp = wx.SplitterWindow(self, -1, style=wx.SP_3D|wx.SP_BORDER)
        self.plot_p = PlotPanel(self.sp,-1)
        self.menu_p = MenuPanel(self.sp,-1)
        pub.subscribe(self.changeStatusbar, 'changeStatusbar')

        # The Status Bar
        self.StatusBar = self.CreateStatusBar(2, wx.ST_SIZEGRIP)

        self.streamlist = []
        self.headerlist = []
        self.currentstreamindex = 0
        self.stream = DataStream() # used for storing original data
        self.plotstream = DataStream() # used for manipulated data
        self.orgheader = {}
        self.shownkeylist = []
        self.keylist = []
        self.flaglist = []
        self.compselect = 'None'
        self.dipathlist = []
        self.divariopath = ''
        self.discalarpath = ''

        self.InitPlotParameter()

        # Try to load ini-file
        # located within home directory
        inipara = loadini()
        print ("INIPARA", inipara)
        if not inipara:
            saveini() # initialize defaultvalues
            inipara = loadini()
            print ("INIPARA", inipara)

        # Variable initializations
        self.initParameter(inipara)

        # Menu Bar
        # --------------
        # Existing shortcuts: o,d,u,s,e,q,c,b,l,a,r,m,i,v  (a,b,c,d,e,f,(gh),i,(jk),l,m,(n),o
        self.MainMenu = wx.MenuBar()
        # ## File Menu
        self.FileMenu = wx.Menu()
        self.FileOpen = wx.MenuItem(self.FileMenu, 101, "&Open File...\tCtrl+O", "Open file", wx.ITEM_NORMAL)
        self.FileMenu.AppendItem(self.FileOpen)
        self.DirOpen = wx.MenuItem(self.FileMenu, 102, "Select &Directory...\tCtrl+D", "Select an existing directory", wx.ITEM_NORMAL)
        self.FileMenu.AppendItem(self.DirOpen)
        self.WebOpen = wx.MenuItem(self.FileMenu, 103, "Open &URL...\tCtrl+U", "Get data from the internet", wx.ITEM_NORMAL)
        self.FileMenu.AppendItem(self.WebOpen)
        self.DBOpen = wx.MenuItem(self.FileMenu, 104, "&Select DB table...\tCtrl+S", "Select a MySQL database", wx.ITEM_NORMAL)
        self.FileMenu.AppendItem(self.DBOpen)
        self.DBOpen.Enable(False)
        self.FileMenu.AppendSeparator()
        self.ExportData = wx.MenuItem(self.FileMenu, 105, "&Export data...\tCtrl+E", "Export data to a file", wx.ITEM_NORMAL)
        self.FileMenu.AppendItem(self.ExportData)
        self.ExportData.Enable(False)
        self.FileMenu.AppendSeparator()
        self.FileQuitItem = wx.MenuItem(self.FileMenu, wx.ID_EXIT, "&Quit\tCtrl+Q", "Quit the program", wx.ITEM_NORMAL)
        self.FileMenu.AppendItem(self.FileQuitItem)
        self.MainMenu.Append(self.FileMenu, "&File")
        # ## Database Menu
        self.DatabaseMenu = wx.Menu()
        self.DBConnect = wx.MenuItem(self.DatabaseMenu, 201, "&Connect MySQL DB...\tCtrl+C", "Connect Database", wx.ITEM_NORMAL)
        self.DatabaseMenu.AppendItem(self.DBConnect)
        self.MainMenu.Append(self.DatabaseMenu, "Data&base")
        # ## DI Menu
        self.DIMenu = wx.Menu()
        self.DIPath2DI = wx.MenuItem(self.DIMenu, 501, "&Load DI data...\tCtrl+L", "Load DI data...", wx.ITEM_NORMAL)
        self.DIMenu.AppendItem(self.DIPath2DI)
        self.DIPath2Vario = wx.MenuItem(self.DIMenu, 502, "Path to &variometer data...\tCtrl+V", "Variometer data...", wx.ITEM_NORMAL)
        self.DIMenu.AppendItem(self.DIPath2Vario)
        self.DIPath2Scalar = wx.MenuItem(self.DIMenu, 503, "Path to scala&r data...\tCtrl+R", "Scalar data...", wx.ITEM_NORMAL)
        self.DIMenu.AppendItem(self.DIPath2Scalar)
        self.DIMenu.AppendSeparator()
        self.DIInputSheet = wx.MenuItem(self.DIMenu, 504, "O&pen input sheet...\tCtrl+P", "Input sheet...", wx.ITEM_NORMAL)
        self.DIMenu.AppendItem(self.DIInputSheet)
        self.MainMenu.Append(self.DIMenu, "D&I")
        # ## Stream Operations
        self.StreamOperationsMenu = wx.Menu()
        self.StreamListSelect = wx.MenuItem(self.StreamOperationsMenu, 601, "Select active Strea&m...\tCtrl+M", "Select Stream", wx.ITEM_NORMAL)
        self.StreamOperationsMenu.AppendItem(self.StreamListSelect)
        self.MainMenu.Append(self.StreamOperationsMenu, "StreamO&perations")
        # ## Options Menu
        self.OptionsMenu = wx.Menu()
        self.OptionsInitItem = wx.MenuItem(self.OptionsMenu, 401, "&Initialisation/Calculation parameter\tCtrl+I", "Modify initialisation/calculation parameters (e.g. filters, sensitivity)", wx.ITEM_NORMAL)
        self.OptionsMenu.AppendItem(self.OptionsInitItem)
        self.OptionsMenu.AppendSeparator()
        self.OptionsObsItem = wx.MenuItem(self.OptionsMenu, 402, "Observator&y specifications\tCtrl+Y", "Modify observatory specific meta data (e.g. pears, offsets)", wx.ITEM_NORMAL)
        self.OptionsMenu.AppendItem(self.OptionsObsItem)
        self.MainMenu.Append(self.OptionsMenu, "&Options")
        self.HelpMenu = wx.Menu()
        self.HelpAboutItem = wx.MenuItem(self.HelpMenu, 301, "&About...", "Display general information about the program", wx.ITEM_NORMAL)
        self.HelpMenu.AppendItem(self.HelpAboutItem)
        self.MainMenu.Append(self.HelpMenu, "&Help")
        self.SetMenuBar(self.MainMenu)
        # Menu Bar end


        self.__set_properties()

        # BindingControls on the menu
        self.Bind(wx.EVT_MENU, self.OnOpenDir, self.DirOpen)
        self.Bind(wx.EVT_MENU, self.OnOpenFile, self.FileOpen)
        self.Bind(wx.EVT_MENU, self.OnOpenURL, self.WebOpen)
        self.Bind(wx.EVT_MENU, self.OnOpenDB, self.DBOpen)
        self.Bind(wx.EVT_MENU, self.OnExportData, self.ExportData)
        self.Bind(wx.EVT_MENU, self.OnFileQuit, self.FileQuitItem)
        self.Bind(wx.EVT_MENU, self.OnDBConnect, self.DBConnect)
        self.Bind(wx.EVT_MENU, self.OnStreamList, self.StreamListSelect)
        self.Bind(wx.EVT_MENU, self.onLoadDI, self.DIPath2DI)
        self.Bind(wx.EVT_MENU, self.onDefineVario, self.DIPath2Vario)
        self.Bind(wx.EVT_MENU, self.onDefineScalar, self.DIPath2Scalar)
        self.Bind(wx.EVT_MENU, self.onInputSheet, self.DIInputSheet)
        self.Bind(wx.EVT_MENU, self.OnOptionsInit, self.OptionsInitItem)
        self.Bind(wx.EVT_MENU, self.OnOptionsObs, self.OptionsObsItem)
        self.Bind(wx.EVT_MENU, self.OnHelpAbout, self.HelpAboutItem)
        # BindingControls on the notebooks
        #       Stream Page
        # ------------------------
        #self.Bind(wx.EVT_BUTTON, self.onOpenStreamButton, self.menu_p.str_page.openStreamButton)
        self.Bind(wx.EVT_BUTTON, self.onTrimStreamButton, self.menu_p.str_page.trimStreamButton)
        self.Bind(wx.EVT_BUTTON, self.onSelectKeys, self.menu_p.str_page.selectKeysButton)
        self.Bind(wx.EVT_BUTTON, self.onExtractData, self.menu_p.str_page.extractValuesButton)
        self.Bind(wx.EVT_BUTTON, self.onChangePlotOptions, self.menu_p.str_page.changePlotButton)
        self.Bind(wx.EVT_BUTTON, self.onRestoreData, self.menu_p.str_page.restoreButton)
        self.Bind(wx.EVT_CHECKBOX, self.onAnnotateCheckBox, self.menu_p.str_page.annotateCheckBox)
        self.Bind(wx.EVT_CHECKBOX, self.onErrorBarCheckBox, self.menu_p.str_page.errorBarsCheckBox)
        self.Bind(wx.EVT_CHECKBOX, self.onConfinexCheckBox, self.menu_p.str_page.confinexCheckBox)
        self.Bind(wx.EVT_BUTTON, self.onDailyMeansButton, self.menu_p.str_page.dailyMeansButton)
        self.Bind(wx.EVT_BUTTON, self.onApplyBCButton, self.menu_p.str_page.applyBCButton)
        self.Bind(wx.EVT_RADIOBOX, self.onChangeComp, self.menu_p.str_page.compRadioBox)
        self.Bind(wx.EVT_RADIOBOX, self.onChangeSymbol, self.menu_p.str_page.symbolRadioBox)
        self.Bind(wx.EVT_BUTTON, self.onFlagOutlierButton, self.menu_p.str_page.flagOutlierButton)
        self.Bind(wx.EVT_BUTTON, self.onFlagSelectionButton, self.menu_p.str_page.flagSelectionButton)
        self.Bind(wx.EVT_BUTTON, self.onFlagRangeButton, self.menu_p.str_page.flagRangeButton)
        self.Bind(wx.EVT_BUTTON, self.onFlagLoadButton, self.menu_p.str_page.flagLoadButton)
        self.Bind(wx.EVT_BUTTON, self.onFlagSaveButton, self.menu_p.str_page.flagSaveButton)
        self.Bind(wx.EVT_BUTTON, self.onFlagDropButton, self.menu_p.str_page.flagDropButton)
        #        Meta Page
        # --------------------------
        #self.Bind(wx.EVT_BUTTON, self.onFilterButton, self.menu_p.met_page.filterButton)
        # Contains General info on top - previously on analysis page
        # add sensor id, sensor name to general info
        # add button with GetFromDB, WriteToDB (only active when DB connected) - WriteToDB only specific dataID or all sensorsID 
        # provide text boxes with data, sensor and station related info
        #     Edit/Review Data related meta data
        #     button
        #     textbox with existing Meta
        #     Edit/Review Sensor related meta data
        #     ....
        #     .... and so on
        self.Bind(wx.EVT_BUTTON, self.onMetaGetDBButton, self.menu_p.met_page.getDBButton)
        self.Bind(wx.EVT_BUTTON, self.onMetaPutDBButton, self.menu_p.met_page.putDBButton)
        self.Bind(wx.EVT_BUTTON, self.onMetaDataButton, self.menu_p.met_page.MetaDataButton)
        self.Bind(wx.EVT_BUTTON, self.onMetaSensorButton, self.menu_p.met_page.MetaSensorButton)
        self.Bind(wx.EVT_BUTTON, self.onMetaStationButton, self.menu_p.met_page.MetaStationButton)
        #        Analysis Page
        # --------------------------
        self.Bind(wx.EVT_BUTTON, self.onDerivativeButton, self.menu_p.ana_page.derivativeButton)
        self.Bind(wx.EVT_BUTTON, self.onRotationButton, self.menu_p.ana_page.rotationButton)
        self.Bind(wx.EVT_BUTTON, self.onFitButton, self.menu_p.ana_page.fitButton)
        self.Bind(wx.EVT_BUTTON, self.onMeanButton, self.menu_p.ana_page.meanButton)
        self.Bind(wx.EVT_BUTTON, self.onMaxButton, self.menu_p.ana_page.maxButton)
        self.Bind(wx.EVT_BUTTON, self.onMinButton, self.menu_p.ana_page.minButton)
        self.Bind(wx.EVT_BUTTON, self.onOffsetButton, self.menu_p.ana_page.offsetButton)
        self.Bind(wx.EVT_BUTTON, self.onFilterButton, self.menu_p.ana_page.filterButton)
        self.Bind(wx.EVT_BUTTON, self.onSmoothButton, self.menu_p.ana_page.smoothButton)
        self.Bind(wx.EVT_BUTTON, self.onActivityButton, self.menu_p.ana_page.activityButton)
        self.Bind(wx.EVT_BUTTON, self.onBaselineButton, self.menu_p.ana_page.baselineButton)
        self.Bind(wx.EVT_BUTTON, self.onDeltafButton, self.menu_p.ana_page.deltafButton)
        self.Bind(wx.EVT_BUTTON, self.onMergeButton, self.menu_p.ana_page.mergeButton)
        self.Bind(wx.EVT_BUTTON, self.onSubtractButton, self.menu_p.ana_page.subtractButton)
        self.Bind(wx.EVT_BUTTON, self.onStackButton, self.menu_p.ana_page.stackButton)
        #        DI Page
        # --------------------------
        self.Bind(wx.EVT_BUTTON, self.onLoadDI, self.menu_p.abs_page.loadDIButton)
        self.Bind(wx.EVT_BUTTON, self.onDefineVario, self.menu_p.abs_page.defineVarioButton)
        self.Bind(wx.EVT_BUTTON, self.onDefineScalar, self.menu_p.abs_page.defineScalarButton)
        self.Bind(wx.EVT_BUTTON, self.onDIAnalyze, self.menu_p.abs_page.AnalyzeButton)
        self.Bind(wx.EVT_BUTTON, self.onDISetParameter, self.menu_p.abs_page.advancedButton)
        self.Bind(wx.EVT_BUTTON, self.onSaveDIData, self.menu_p.abs_page.SaveLogButton)
        self.Bind(wx.EVT_BUTTON, self.onClearDIData, self.menu_p.abs_page.ClearLogButton)
        #        Report Page
        # --------------------------
        self.Bind(wx.EVT_BUTTON, self.onSaveLogButton, self.menu_p.rep_page.saveLoggerButton)
        self.menu_p.rep_page.logMsg('Begin logging...')
        # Eventually kill this redirection because it might cause problems from other classes
        #redir=RedirectText(self.menu_p.rep_page.logMsg) # Start redirecting stdout to log window
        #sys.stdout=redir
        #        Monitor Page
        # --------------------------
        self.Bind(wx.EVT_BUTTON, self.onConnectMARCOSButton, self.menu_p.com_page.getMARCOSButton)
        self.Bind(wx.EVT_BUTTON, self.onConnectMARTASButton, self.menu_p.com_page.getMARTASButton)
        self.Bind(wx.EVT_BUTTON, self.onConnectMQTTButton, self.menu_p.com_page.getMQTTButton)
        self.Bind(wx.EVT_BUTTON, self.onStartMonitorButton, self.menu_p.com_page.startMonitorButton)
        self.Bind(wx.EVT_BUTTON, self.onStopMonitorButton, self.menu_p.com_page.stopMonitorButton)
        self.Bind(wx.EVT_BUTTON, self.onLogDataButton, self.menu_p.com_page.saveMonitorButton)

        # Connect to database
        self._db_connect(self.host, self.user, self.passwd, self.dbname)


        # Disable yet unavailbale buttons
        # --------------------------
        self.DeactivateAllControls()

        self.sp.SplitVertically(self.plot_p,self.menu_p,900)

    def __set_properties(self):
        self.SetTitle("MagPy")
        self.SetSize((1300, 800))
        self.SetFocus()
        self.StatusBar.SetStatusWidths([-1, -1])
        # statusbar fields
        StatusBar_fields = ["Ready", ""]
        for i in range(len(StatusBar_fields)):
            self.StatusBar.SetStatusText(StatusBar_fields[i], i)
        self.menu_p.SetMinSize((100, 100))
        self.plot_p.SetMinSize((100, 100))


    def InitPlotParameter(self):
        # Kwargs for plotting
        self.annotate = True
        self.menu_p.str_page.annotateCheckBox.SetValue(True)
        self.errorbars = False
        self.menu_p.str_page.errorBarsCheckBox.SetValue(False)
        self.confinex = False
        self.menu_p.str_page.confinexCheckBox.SetValue(False)
        self.fullday = False
        self.includeid = False
        self.grid = True
        self.padding = None
        self.specialdict={}
        self.colorlist = ['b','g','m','c','y','k','b','g','m','c','y','k']
        self.stormphases=None
        self.t_stormphases={}
        self.function=None
        self.plottype='discontinuous'
        self.labels=False
        self.resolution=None
        self.monitorSource=None
        lenkeys = len(self.shownkeylist)
        self.symbollist=['-']*len(self.shownkeylist)
        collist=['b','g','m','c','y','k','b','g','m','c','y','k']
        self.plotopt = {'labels':'None' , 'padding': 'None', 'stormphases': 'False', 'specialdict': 'None', 'bartrange':'None', 'bgcolor': 'white', 'colorlist': ",".join(collist[:lenkeys]) ,'fullday':'False', 'grid':'True','gridcolor':'#316931', 'includeid':'False', 'labelcolor':'0.2', 'legendposition':'upper left', 'plottitle':'', 'plottype':'discontinuous', 'symbollist':",".join(self.symbollist),'t_stormphases':'None', 'opacity':'0.0'}

        """
        self.bartrange = 0
        self.bgcolor='white'
        self.function = {}
        self.gridcolor = '#316931'
        self.labelcolor = '0.2'
        self.opacity = 0.0
        self.legendposition = 'upper left'
        self.plottitle = None
        """

    def initParameter(self, dictionary):
        # Variable initializations
        self.dbname = dictionary['dbname']
        self.user = dictionary['user']
        pwd = dictionary['passwd']
        self.passwd = base64.b64decode(pwd)
        self.host = dictionary['host']
        self.dirname = dictionary['dirname']

        self.symbolselect = 0
        self.bascompselect = dictionary['basecompselect']

        self.dipathlist = dictionary['dipathlist']
        self.divariopath = dictionary['divariopath']
        self.discalarpath = dictionary['discalarpath']
        self.diexpD = dictionary['diexpD']
        self.diexpI = dictionary['diexpI']
        self.stationid = dictionary['stationid']
        self.diid = dictionary['diid']
        self.ditype = dictionary['ditype'] #abstype
        self.diazimuth = dictionary['diazimuth']
        self.dipier = dictionary['dipier']
        self.dialpha = dictionary['dialpha']
        self.dideltaF = dictionary['dideltaF']
        self.didbadd = dictionary['didbadd']


    # ################
    # Updating and reinitiatzation methods:

    def DeactivateAllControls(self):
        """
        DESCRIPTION
            To be used at start and when an empty stream is loaded
            Deactivates all control elements
        """
        # Menu
        self.ExportData.Enable(False)

        # Stream
        self.menu_p.str_page.pathTextCtrl.Disable()        # remain disabled
        self.menu_p.str_page.fileTextCtrl.Disable()        # remain disabled
        self.menu_p.str_page.startDatePicker.Disable()     # always
        self.menu_p.str_page.startTimePicker.Disable()     # always
        self.menu_p.str_page.endDatePicker.Disable()       # always
        self.menu_p.str_page.endTimePicker.Disable()       # always
        ## TODO Modify method below - when directory/database is selected, automatically open dialog
        ## to modify time range and other read options
        #self.menu_p.str_page.openStreamButton.Disable()
        self.menu_p.str_page.trimStreamButton.Disable()    # always
        self.menu_p.str_page.restoreButton.Disable()       # always
        self.menu_p.str_page.selectKeysButton.Disable()    # always
        self.menu_p.str_page.extractValuesButton.Disable() # always
        self.menu_p.str_page.changePlotButton.Disable()    # always
        self.menu_p.str_page.flagOutlierButton.Disable()   # always
        self.menu_p.str_page.flagSelectionButton.Disable() # always
        self.menu_p.str_page.flagRangeButton.Disable()     # always
        self.menu_p.str_page.flagLoadButton.Disable()      # always
        self.menu_p.str_page.flagDropButton.Disable()      # activated if annotation are present
        self.menu_p.str_page.flagSaveButton.Disable()      # activated if annotation are present 
        self.menu_p.str_page.dailyMeansButton.Disable()    # activated for DI data
        self.menu_p.str_page.applyBCButton.Disable()       # activated if DataAbsInfo is present
        self.menu_p.str_page.annotateCheckBox.Disable()    # activated if annotation are present
        self.menu_p.str_page.errorBarsCheckBox.Disable()   # activated delta columns are present and not DI file
        self.menu_p.str_page.confinexCheckBox.Disable()    # always
        self.menu_p.str_page.compRadioBox.Disable()        # activated if xyz,hdz or idf
        self.menu_p.str_page.symbolRadioBox.Disable()      # activated if less then 2000 points, active if DI data

        # Meta
        self.menu_p.met_page.getDBButton.Disable()         # activated when DB is connected
        self.menu_p.met_page.putDBButton.Disable()         # activated when DB is connected
        self.menu_p.met_page.MetaDataButton.Disable()      # remain disabled
        self.menu_p.met_page.MetaSensorButton.Disable()    # remain disabled
        self.menu_p.met_page.MetaStationButton.Disable()   # remain disabled
        self.menu_p.met_page.stationTextCtrl.Disable()     # remain disabled
        self.menu_p.met_page.sensorTextCtrl.Disable()      # remain disabled
        self.menu_p.met_page.dataTextCtrl.Disable()        # remain disabled
        # DI
        self.menu_p.abs_page.AnalyzeButton.Disable()       # activate if DI data is present i.e. diTextCtrl contains data
        self.menu_p.abs_page.loadDIButton.Enable()         # remain enabled
        self.menu_p.abs_page.diTextCtrl.Disable()          # remain disabled
        self.menu_p.abs_page.defineVarioButton.Enable()    # remain enabled
        self.menu_p.abs_page.varioTextCtrl.Disable()       # remain disabled
        self.menu_p.abs_page.defineScalarButton.Enable()   # remain enabled
        self.menu_p.abs_page.scalarTextCtrl.Disable()      # remain disabled
        self.menu_p.abs_page.dilogTextCtrl.Disable()       # remain disabled
        self.menu_p.abs_page.ClearLogButton.Disable()      # Activate if log contains text
        self.menu_p.abs_page.SaveLogButton.Disable()      # Activate if log contains text
        # Analysis
        self.menu_p.ana_page.rotationButton.Disable()      # if xyz magnetic data
        self.menu_p.ana_page.derivativeButton.Disable()    # always
        self.menu_p.ana_page.fitButton.Disable()           # always
        self.menu_p.ana_page.meanButton.Disable()          # always
        self.menu_p.ana_page.maxButton.Disable()           # always
        self.menu_p.ana_page.minButton.Disable()           # always
        self.menu_p.ana_page.offsetButton.Disable()        # always
        self.menu_p.ana_page.filterButton.Disable()        # always
        self.menu_p.ana_page.smoothButton.Disable()        # always
        self.menu_p.ana_page.activityButton.Disable()      # if xyz, hdz magnetic data
        self.menu_p.ana_page.baselineButton.Disable()      # if absstream in streamlist
        self.menu_p.ana_page.deltafButton.Disable()        # if xyzf available
        self.menu_p.ana_page.mergeButton.Disable()         # if len(self.streamlist) > 1
        self.menu_p.ana_page.subtractButton.Disable()      # if len(self.streamlist) > 1
        self.menu_p.ana_page.stackButton.Disable()         # if len(self.streamlist) > 1

        # Report
        self.menu_p.rep_page.logger.Disable()              # remain disabled

        # Monitor
        self.menu_p.com_page.connectionLogTextCtrl.Disable()  # remain disabled
        self.menu_p.com_page.startMonitorButton.Disable()  # always
        self.menu_p.com_page.stopMonitorButton.Disable()   # always
        self.menu_p.com_page.saveMonitorButton.Disable()   # always
        self.menu_p.com_page.coverageTextCtrl.Disable()    # always
        self.menu_p.com_page.frequSlider.Disable()         # always
        self.menu_p.com_page.marcosLabel.SetBackgroundColour((255,23,23))
        self.menu_p.com_page.martasLabel.SetBackgroundColour((255,23,23))
        self.menu_p.com_page.mqttLabel.SetBackgroundColour((255,23,23))
        self.menu_p.com_page.marcosLabel.SetValue('not connected')
        self.menu_p.com_page.martasLabel.SetValue('not connected')
        self.menu_p.com_page.mqttLabel.SetValue('not connected')

    def ActivateControls(self,stream):
        """
        DESCRIPTION
            Checks contents of stream and state of program.
            Activates controls in dependency of the checks
        """
        # initially reset all controls
        self.DeactivateAllControls()
        if not len(stream.ndarray[0]) > 0:
            self.changeStatusbar("No data available")
            return

        # Always part
        # --------------------------------
        # Length
        n = stream.length()[0]
        keys = stream._get_key_headers()
        keystr = ','.join(keys)

        keylist = [elem for elem in keys if elem in NUMKEYLIST]
        self.shownkeylist = keylist[:9]
        #print (self.menu_p.str_page.symbolRadioBox.GetStringSelection())
        if self.menu_p.str_page.symbolRadioBox.GetStringSelection() == 'line':
            self.symbollist = ['-'] * len(self.shownkeylist)
        else:
            self.symbollist = ['o'] * len(self.shownkeylist)

        # Sampling rate
        try:
            sr = stream.samplingrate()
        except:
            print ("Sampling rate determinations failed - might happen in DI files")
            sr = 9999
        # Coverage
        ind = np.argmin(stream.ndarray[0].astype(float))
        mintime = stream._get_min('time')
        maxtime = stream._get_max('time')
        # Flag column
        commidx = KEYLIST.index('comment')
        commcol = stream.ndarray[commidx]
        commcol = np.asarray([el for el in commcol if not el in ['','-',np.nan]])
        # Delta
        deltas = False
        if 'dx' in keys or 'dy' in keys or 'dz' in keys or 'df' in keys:
            deltas = True
        # Essential header info
        comps = stream.header.get('DataComponents','')[:3]
        sensorid = stream.header.get('SensorID','')
        dataid = self.plotstream.header.get('DataID','')
        formattype = self.plotstream.header.get('DataFormat','')
        absinfo = self.plotstream.header.get('DataAbsInfo',None)
        metadatatext = ''
        metasensortext = ''
        metastationtext = ''
        for key in stream.header:
            #print ("Activate", key)
            if key.startswith('Data'):
                 value = stream.header.get(key,'')
                 #try:  # python 3
                 if not isinstance(value, str):
                     try: 
                         if self.plotstream._is_number(value):
                             pass
                         else:
                             value = 'list'
                     except:
                         value = 'list'
                 #print ("-- ", value)
                 metadatatext += "{}: \t{}\n".format(key.replace('Data',''),value)
            if key.startswith('Sensor'):
                 metasensortext += "{}: \t{}\n".format(key.replace('Sensor',''),stream.header.get(key,'')) # key.replace('Sensor','')+': \t'+stream.header.get(key,'')+'\n'
            if key.startswith('Station'):
                 metastationtext += "{}: \t{}\n".format(key.replace('Station',''),stream.header.get(key,'')) #key.replace('Station','')+': \t'+stream.header.get(key,'')+'\n'


        # Activate "always" fields
        # ----------------------------------------
        # menu
        self.ExportData.Enable(True)

        # ----------------------------------------
        # stream page
        self.menu_p.str_page.startDatePicker.Enable()     # always
        self.menu_p.str_page.startTimePicker.Enable()     # always
        self.menu_p.str_page.endDatePicker.Enable()       # always
        self.menu_p.str_page.endTimePicker.Enable()       # always
        self.menu_p.str_page.trimStreamButton.Enable()    # always
        self.menu_p.str_page.restoreButton.Enable()       # always
        self.menu_p.str_page.selectKeysButton.Enable()    # always
        self.menu_p.str_page.extractValuesButton.Enable() # always
        self.menu_p.str_page.changePlotButton.Enable()    # always
        self.menu_p.str_page.flagOutlierButton.Enable()   # always
        self.menu_p.str_page.flagSelectionButton.Enable() # always
        self.menu_p.str_page.flagRangeButton.Enable()     # always
        self.menu_p.str_page.flagLoadButton.Enable()      # always
        self.menu_p.str_page.confinexCheckBox.Enable()    # always
        self.menu_p.met_page.MetaDataButton.Enable()      # always
        self.menu_p.met_page.MetaSensorButton.Enable()    # always
        self.menu_p.met_page.MetaStationButton.Enable()   # always

        # ----------------------------------------
        # analysis page
        self.menu_p.ana_page.derivativeButton.Enable()    # always
        self.menu_p.ana_page.fitButton.Enable()           # always
        self.menu_p.ana_page.meanButton.Enable()          # always
        self.menu_p.ana_page.maxButton.Enable()           # always
        self.menu_p.ana_page.minButton.Enable()           # always
        self.menu_p.ana_page.offsetButton.Enable()        # always
        self.menu_p.ana_page.filterButton.Enable()        # always
        self.menu_p.ana_page.smoothButton.Enable()        # always


        # Selective fields
        # ----------------------------------------
        if comps in ['xyz','XYZ','hdz','HDZ','idf','IDF']:
            self.menu_p.str_page.compRadioBox.Enable()
        if len(commcol) > 0:
            self.menu_p.str_page.flagDropButton.Enable()     # activated if annotation are present
            self.menu_p.str_page.flagSaveButton.Enable()      # activated if annotation are present 
            self.menu_p.str_page.annotateCheckBox.Enable()    # activated if annotation are present
        if formattype == 'MagPyDI':
            self.menu_p.str_page.dailyMeansButton.Enable()    # activated for DI data
            self.menu_p.str_page.symbolRadioBox.Enable()      # activated for DI data
        if not absinfo == None:
            self.menu_p.str_page.applyBCButton.Enable()       # activated if DataAbsInfo is present
        if deltas:
            self.menu_p.str_page.errorBarsCheckBox.Enable()   # activated delta columns are present and not DI file
        if n < 2000:
            self.menu_p.str_page.symbolRadioBox.Enable()      # activated if less then 2000 points, active if DI data
        if not dataid == '' and self.db:
            self.menu_p.met_page.getDBButton.Enable()         # activated when DB is connected
            self.menu_p.met_page.putDBButton.Enable()         # activated when DB is connected
        if not str(self.menu_p.abs_page.dilogTextCtrl.GetValue()) == '':
            self.menu_p.abs_page.ClearLogButton.Enable()
            self.menu_p.abs_page.SaveLogButton.Enable()

        if 'x' in keys and 'y' in keys and 'z' in keys:
            self.menu_p.ana_page.rotationButton.Enable()      # activate if vector appears to be present
            self.menu_p.ana_page.activityButton.Enable()      # activate if vector appears to be present
            if 'f' in keys and not 'df' in keys:
                self.menu_p.ana_page.deltafButton.Enable()    # activate if full vector present
        

        # Update "information" fields
        # ----------------------------------------
        self.menu_p.met_page.amountTextCtrl.SetValue(str(n))
        self.menu_p.met_page.samplingrateTextCtrl.SetValue(str(sr))
        self.menu_p.met_page.keysTextCtrl.SetValue(keystr)
        self.menu_p.met_page.typeTextCtrl.SetValue(formattype)
        self.menu_p.str_page.startDatePicker.SetValue(pydate2wxdate(num2date(mintime)))
        self.menu_p.str_page.endDatePicker.SetValue(pydate2wxdate(num2date(maxtime)))
        self.menu_p.str_page.startTimePicker.SetValue(num2date(mintime).strftime('%X'))
        self.menu_p.str_page.endTimePicker.SetValue(num2date(maxtime).strftime('%X'))
        self.menu_p.rep_page.logMsg('- found {} data points'.format(len(stream.ndarray[0])))

        self.menu_p.met_page.dataTextCtrl.SetValue(metadatatext)
        self.menu_p.met_page.sensorTextCtrl.SetValue(metasensortext)
        self.menu_p.met_page.stationTextCtrl.SetValue(metastationtext)


    def InitialRead(self,stream):
        """
        DESCRIPTION
            Backups stream content and adds current strem and header info to streamlist and headerlist.
            Creates plotstream copy and stores pointer towards lists.
            Checks whether ndarray is resent and whether data is present at all
        """

        if not len(stream.ndarray[0]) > 0:
            stream = stream.linestruct2ndarray()
        if not len(stream.ndarray[0]) > 0:
            self.DeactivateAllControls()
            self.changeStatusbar("No data available")
            return False
        self.stream = stream

        self.plotstream = self.stream.copy()
        currentstreamindex = len(self.streamlist)
        self.streamlist.append(self.stream)
        self.headerlist.append(self.stream.header)
        self.currentstreamindex = currentstreamindex
        return True

    """
    def CheckStreamContent(self, stream):

        if not len(stream.ndarray[0]) > 0:
            stream = stream.linestruct2ndarray()
        if not len(stream.ndarray[0]) > 0:
            self.DeactivateAllControls()
            self.changeStatusbar("No data available")
            return False

        self.stream = stream
        
        self.ActivateControls(stream)

        # Check Header contents
        if not stream.header.get('DataComponents','')[:3] in ['xyz','XYZ','hdz','HDZ','idf','IDF']:
            print ("DataComponents failure", stream.header.get('DataComponents',''))
            self.menu_p.str_page.compRadioBox.Disable()

        # Update Text windowsand their contents
        #self.SetPageValues(stream)

        # Avtivate/Deactivate page contents and buttons
        self.menu_p.str_page.openStreamButton.Disable()
  
        self.changeStatusbar("Ready")
        return True


    def ReactivateStreamPage(self):
            self.menu_p.str_page.fileTextCtrl.Enable()
            self.menu_p.str_page.pathTextCtrl.Enable()
            self.menu_p.str_page.startDatePicker.Enable()
            self.menu_p.str_page.endDatePicker.Enable()
            self.menu_p.str_page.startTimePicker.Enable()
            self.menu_p.str_page.endTimePicker.Enable()
            self.menu_p.str_page.openStreamButton.Enable()

    def SetPageValues(self, stream):
        Method to update all pages with the streams values
        # Length
        n = stream.length()[0]
        # keys
        keys = stream._get_key_headers()
        keystr = ','.join(keys)
        # Sampling rate
        sr = stream.samplingrate()
        # Coverage
        ind = np.argmin(stream.ndarray[0].astype(float))
        mintime = stream._get_min('time')
        maxtime = stream._get_max('time')

        self.menu_p.met_page.amountTextCtrl.SetValue(str(n))
        self.menu_p.met_page.samplingrateTextCtrl.SetValue(str(sr))
        self.menu_p.met_page.keysTextCtrl.SetValue(keystr)
        #print(wx.DateTimeFromTimeT(time.mktime(num2date(mintime).timetuple())))
        self.menu_p.str_page.startDatePicker.SetValue(wx.DateTimeFromTimeT(time.mktime(num2date(mintime).timetuple())))
        self.menu_p.str_page.endDatePicker.SetValue(wx.DateTimeFromTimeT(time.mktime(num2date(maxtime).timetuple())))
        self.menu_p.str_page.startTimePicker.SetValue(num2date(mintime).strftime('%X'))
        self.menu_p.str_page.endTimePicker.SetValue(num2date(maxtime).strftime('%X'))
        self.menu_p.rep_page.logMsg('- %i data point loaded' % len(stream.ndarray[0]))

    def UpdateTimeRanges(self,stream):
            mintime = stream._get_min('time')
            maxtime = stream._get_max('time')
            self.menu_p.str_page.startDatePicker.SetValue(wx.DateTimeFromTimeT(time.mktime(num2date(mintime).timetuple())))
            self.menu_p.str_page.endDatePicker.SetValue(wx.DateTimeFromTimeT(time.mktime(num2date(maxtime).timetuple())))
            self.menu_p.str_page.startTimePicker.SetValue(num2date(mintime).strftime('%X'))
            self.menu_p.str_page.endTimePicker.SetValue(num2date(maxtime).strftime('%X'))
            #self.menu_p.str_page.startDatePicker.Disable()
            #self.menu_p.str_page.endDatePicker.Disable()
            #self.menu_p.str_page.startTimePicker.Disable()
            #self.menu_p.str_page.endTimePicker.Disable()
            self.menu_p.str_page.openStreamButton.Disable()
    """

 
    def UpdatePlotCharacteristics(self,stream):
        """
        DESCRIPTION
            Activates specific menus and buttons in dependeny of data content
            Updating time ranges on Stream page
        """

        # Some general Checks on Stream
        # ##############################
        # 1. Preslect first nine keys and set up default options
        keylist = []
        keylist = stream._get_key_headers(limit=9)
        # TODO: eventually remove keys with high percentage of nans
        #for key in keylist:
        #    ar = [eval('elem.'+key) for elem in stream if not isnan(eval('elem.'+key))]
        #    div = float(len(ar))/float(len(stream))*100.0
        #    if div <= 5.:
        #        keylist.remove(key)
        keylist = [elem for elem in keylist if elem in NUMKEYLIST]
        self.symbollist = ['-'] * len(keylist)
        self.menu_p.str_page.compRadioBox.SetStringSelection('line')
        self.menu_p.str_page.dailyMeansButton.Disable()


        # 2. If stream too long then don't allow scatter plots -- too slowly
        if stream.length()[0] < 2000:
            self.menu_p.str_page.symbolRadioBox.Enable()
        else:
            self.menu_p.str_page.symbolRadioBox.Disable()
        # 3. If DataFormat = MagPyDI then preselect scatter, and idf and basevalues
        if stream.header.get('DataFormat') == 'MagPyDI':
            self.menu_p.str_page.symbolRadioBox.Enable()
            self.menu_p.str_page.symbolRadioBox.SetStringSelection('point')
            self.shownkeylist = keylist
            keylist = ['x','y','z','dx','dy','dz']
            self.symbollist = ['o'] * len(keylist)
            # enable daily average button
            self.menu_p.str_page.dailyMeansButton.Enable()

        self.shownkeylist = keylist

        # 4. If DataFormat = MagPyDI then preselect scatter, and idf and basevalues
        typus = stream.header.get('DataComponents')
        try:
            typus = typus.lower()[:3]
        except:
            typus = ''
        if typus in ['xyz','hdz','idf']:            
            self.compselect = typus
            self.menu_p.str_page.compRadioBox.Enable()
            self.menu_p.str_page.compRadioBox.SetStringSelection(self.compselect)
        else:
            if 'x' in keylist and 'y' in keylist and 'z' in keylist:
                self.compselect = 'xyz'
                self.menu_p.str_page.compRadioBox.Enable()

        # 5. Baseline correction if Object contained in stream
        #if stream.header.get('DataAbsFunctionObject'):
        #    self.menu_p.str_page.applyBCButton.Enable()
        #else:
        #    self.menu_p.str_page.applyBCButton.Disable()

        return keylist


    def defaultFileDialogOptions(self):
        ''' Return a dictionary with file dialog options that can be
            used in both the save file dialog as well as in the open
            file dialog. '''
        return dict(message='Choose a file', defaultDir=self.dirname,
                    wildcard='*.*')

    def askUserForFilename(self, **dialogOptions):
        dialog = wx.FileDialog(self, **dialogOptions)
        if dialog.ShowModal() == wx.ID_OK:
            userProvidedFilename = True
            self.filename = dialog.GetFilename()
            self.dirname = dialog.GetDirectory()
            #self.SetTitle() # Update the window title with the new filename
        else:
            userProvidedFilename = False
        dialog.Destroy()
        return userProvidedFilename



    def OnInitialPlot(self, stream):
        """
        DEFINITION:
            read stream, extract columns with values and display up to three of them by defailt
            executes guiPlot then
        """
        #if not len(stream.ndarray[0]) > 0:
        #    stream = stream.linestruct2ndarray()
        #self.stream = stream
        #self.plotstream = stream.copy()
        #self.orgheader = stream.header

        self.changeStatusbar("Plotting...")

        keylist = self.UpdatePlotCharacteristics(self.plotstream)        

        self.menu_p.rep_page.logMsg('- keys: %s' % (', '.join(keylist)))
        #if len(stream) > self.resolution:
        #    self.menu_p.rep_page.logMsg('- warning: resolution of plot reduced by a factor of %i' % (int(len(stream)/self.resolution)))

        self.plot_p.guiPlot(self.plotstream,keylist,symbollist=self.symbollist,annotate=self.annotate)

        """
        if stream.length()[0] > 0 and len(keylist) > 0:
            self.ExportData.Enable(True)
            self.menu_p.ana_page.activityButton.Enable() # enabled at initial plot
            self.menu_p.ana_page.offsetButton.Enable()
            self.menu_p.ana_page.fitButton.Enable()
            self.menu_p.ana_page.activityButton.Enable()
            self.menu_p.ana_page.filterButton.Enable()
            self.menu_p.ana_page.outlierButton.Enable()
            self.menu_p.ana_page.derivativeButton.Enable()
            self.menu_p.ana_page.rotationButton.Enable()
        """

        self.changeStatusbar("Ready")

    def OnPlot(self, stream, keylist, padding=None, specialdict={},errorbars=None,
        colorlist=None,symbollist=None,annotate=None,stormphases=None,
        t_stormphases={},includeid=False,function=None,plottype='discontinuous',
        labels=False,resolution=None, confinex=False, plotopt=None):
        """
        DEFINITION:
            read stream and display
        """
        self.changeStatusbar("Plotting...")
        #print ("ConfineX:", confinex, symbollist)
        self.plot_p.guiPlot(stream,keylist,padding=padding,specialdict=specialdict,errorbars=errorbars,
                            colorlist=colorlist,symbollist=symbollist,annotate=annotate,
                            includeid=includeid, function=function,plottype=plottype,                 
                            labels=labels,resolution=resolution,confinex=confinex,plotopt=plotopt)
        #self.plot_p.guiPlot(stream,keylist,**kwargs)
        if stream.length()[0] > 1 and len(keylist) > 0:
            self.ExportData.Enable(True)
        self.changeStatusbar("Ready")


    # ################
    # Top menu methods:


    def OnHelpAbout(self, event):

        description = """MagPy is developed for geomagnetic analysis.
Features include a support of many data formats, visualization,
advanced anaylsis routines, url/database accessability, DI analysis,
non-geomagnetic data support and more.
"""

        licence = """MagPy is free software; you can redistribute
it and/or modify it under the terms of the GNU General Public License as
published by the Free Software Foundation; either version 2 of the License,
or any later version.

MagPy is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the GNU General Public License for more details. You should have
received a copy of the GNU General Public License along with MagPy;
if not, write to the Free Software Foundation, Inc., 59 Temple Place,
Suite 330, Boston, MA  02111-1307  USA"""


        info = wx.AboutDialogInfo()

        info.SetIcon(wx.Icon('magpy128.xpm', wx.BITMAP_TYPE_XPM))
        info.SetName('MagPy')
        info.SetVersion(__version__)
        info.SetDescription(description)
        info.SetCopyright('(C) 2011 - 2016 Roman Leonhardt')
        info.SetWebSite('http://www.conrad-observatory.at')
        info.SetLicence(licence)
        info.AddDeveloper('Roman Leonhardt, Rachel Bailey')
        info.AddDocWriter('Leonhardt,Bailey')
        info.AddArtist('Leonhardt')
        info.AddTranslator('Bailey')

        wx.AboutBox(info)

    def OnExit(self, event):
        self.Close()  # Close the main window.

    def OnOpenDir(self, event):
        stream = DataStream()
        dialog = wx.DirDialog(None, "Choose a directory:",self.dirname,style=wx.DD_DEFAULT_STYLE | wx.DD_NEW_DIR_BUTTON)
        if dialog.ShowModal() == wx.ID_OK:
            filelist = glob.glob(os.path.join(dialog.GetPath(),'*'))
            self.dirname = dialog.GetPath() # modify self.dirname
            files = sorted(filelist, key=os.path.getmtime)
            oldest = extractDateFromString(files[0])[0]
            old  = wx.DateTimeFromTimeT(time.mktime(oldest.timetuple()))
            newest = extractDateFromString(files[-1])[0]
            newest = newest+timedelta(days=1)
            new  = wx.DateTimeFromTimeT(time.mktime(newest.timetuple()))
            self.menu_p.str_page.pathTextCtrl.SetValue(dialog.GetPath())
            self.menu_p.str_page.fileTextCtrl.SetValue("*")
            #self.changeStatusbar("Loading data ...")
        dialog.Destroy()

        stream = self.openStream(path=self.dirname,mintime=old, maxtime=new, extension='*')

        if self.InitialRead(stream):
            self.ActivateControls(self.plotstream)
            self.OnInitialPlot(self.plotstream)


    def OnOpenFile(self, event):
        self.dirname = ''
        stream = DataStream()
        stream.header = {}
        filelist = []
        dlg = wx.FileDialog(self, "Choose a file", self.dirname, "", "*.*", wx.MULTIPLE)
        if dlg.ShowModal() == wx.ID_OK:
            self.changeStatusbar("Loading data ...")
            pathlist = dlg.GetPaths()
            for path in pathlist:
                elem = os.path.split(path)
                self.dirname = elem[0]
                filelist.append(elem[1])
                self.changeStatusbar(path)
                tmp = read(path)
                self.changeStatusbar("... found {} rows".format(tmp.length()[0]))
                stream.extend(tmp.container,tmp.header,tmp.ndarray)
            #stream = read(path_or_url=os.path.join(self.dirname, self.filename),tenHz=True,gpstime=True)
            #self.menu_p.str_page.lengthStreamTextCtrl.SetValue(str(len(stream)))
            self.filename = ' ,'.join(filelist)
            self.menu_p.str_page.fileTextCtrl.SetValue(self.filename)
            self.menu_p.str_page.pathTextCtrl.SetValue(self.dirname)

        dlg.Destroy()

        # plot data
        if self.InitialRead(stream):
            self.ActivateControls(self.plotstream)
            self.OnInitialPlot(self.plotstream)


    def OnOpenURL(self, event):
        stream = DataStream()
        bookmarks = ['http://www.intermagnet.org/test/ws/?id=BOU','ftp://ftp.nmh.ac.uk/wdc/obsdata/hourval/single_year/2011/fur2011.wdc','ftp://user:passwd@www.zamg.ac.at/data/magnetism/wic/variation/WIC20160627pmin.min','http://www.conrad-observatory.at/zamg/index.php/downloads-en/category/13-definite2015?download=66:wic-2015-0000-pt1m-4','http://www-app3.gfz-potsdam.de/kp_index/qlyymm.tab']
        
        dlg = OpenWebAddressDialog(None, title='Open URL', favorites=bookmarks)
        if dlg.ShowModal() == wx.ID_OK:
            url = dlg.urlTextCtrl.GetValue()
            self.changeStatusbar("Loading data ... be patient")
            if not url.endswith('/'):
                self.menu_p.str_page.pathTextCtrl.SetValue(url)
                self.menu_p.str_page.fileTextCtrl.SetValue(url.split('/')[-1])
                try:
                    stream = read(path_or_url=url)
                except:
                    dlg = wx.MessageDialog(self, "Could not access URL!\n"
                        "please check address or your internet connection\n",
                        "OpenWebAddress", wx.OK|wx.ICON_INFORMATION)
                    dlg.ShowModal()
                    self.changeStatusbar("Loading url failed ... Ready")
                    dlg.Destroy()
            else:
                self.menu_p.str_page.pathTextCtrl.SetValue(url)
                mintime = pydate2wxdate(datetime(1777,4,30))  # Gauss
                maxtime = pydate2wxdate(datetime(2233,3,22))  # Kirk
                try:
                    stream = self.openStream(path=url, mintime=mintime, maxtime=maxtime, extension='*')
                except:
                    dlg = wx.MessageDialog(self, "Could not access URL!\n"
                        "please check address or your internet connection\n",
                        "OpenWebAddress", wx.OK|wx.ICON_INFORMATION)
                    dlg.ShowModal()
                    self.changeStatusbar("Loading url failed ... Ready")
                    dlg.Destroy()

            #if not bookmarks_old == dlg.favorites:
            #    print ("Favorites have changed ...  modify init")
            
        if self.InitialRead(stream):
            self.ActivateControls(self.plotstream)
            self.OnInitialPlot(self.plotstream)

        self.changeStatusbar("Ready")
        dlg.Destroy()


    def OnOpenDB(self, event):
        # a) get all DATAINFO IDs and store them in a list
        # b) disable pathTextCtrl (DB: dbname)
        # c) Open dialog which lets the user select list and time window
        # d) update stream menu
        getdata = False
        stream = DataStream()
        if self.db:
            self.menu_p.rep_page.logMsg('- Accessing database ...')
            cursor = self.db.cursor()
            sql = "SELECT DataID, DataMinTime, DataMaxTime FROM DATAINFO"
            cursor.execute(sql)
            output = cursor.fetchall()
            datainfoidlist = [elem[0] for elem in output]
            if len(datainfoidlist) < 1:
                dlg = wx.MessageDialog(self, "No data tables available!\n"
                            "please check your database\n",
                            "OpenDB", wx.OK|wx.ICON_INFORMATION)
                dlg.ShowModal()
                dlg.Destroy()
                return
            dlg = DatabaseContentDialog(None, title='MySQL Database: Get content',datalst=datainfoidlist)
            if dlg.ShowModal() == wx.ID_OK:
                datainfoid = dlg.dataComboBox.GetValue()
                stream = DataStream()
                mintime = stream._testtime([elem[1] for elem in output if elem[0] == datainfoid][0])
                lastupload = stream._testtime([elem[2] for elem in output if elem[0] == datainfoid][0])
                maxtime = stream._testtime(datetime.strftime(lastupload,'%Y-%m-%d'))+timedelta(days=1)
                self.menu_p.str_page.pathTextCtrl.SetValue('MySQL Database')
                self.menu_p.str_page.fileTextCtrl.SetValue(datainfoid)
                getdata = True
            dlg.Destroy()
        else:
            dlg = wx.MessageDialog(self, "Could not access database!\n"
                        "please check your connection\n",
                        "OpenDB", wx.OK|wx.ICON_INFORMATION)
            dlg.ShowModal()
            dlg.Destroy()
            return

        if getdata:
            path = [self.db,datainfoid]
            stream = self.openStream(path=path,mintime=pydate2wxdate(mintime), maxtime=pydate2wxdate(maxtime),extension='MySQL Database')

            if self.InitialRead(stream):
                self.ActivateControls(self.plotstream)
                self.OnInitialPlot(self.plotstream)


    def OnExportData(self, event):
        dlg = ExportDataDialog(None, title='Export Data')
        if dlg.ShowModal() == wx.ID_OK:
            filenamebegins = dlg.beginTextCtrl.GetValue()
            filenameends = dlg.endTextCtrl.GetValue()
            datetyp = dlg.dateComboBox.GetValue()
            if datetyp == '2000-11-22':
                dateformat = '%Y-%m-%d'
            elif datetyp == '20001122':
                dateformat = '%Y%m%d'
            else:
                dateformat = '%b%d%y'
            path = dlg.selectedTextCtrl.GetValue()
            fileformat = dlg.formatComboBox.GetValue()
            coverage = dlg.coverageComboBox.GetValue()
            if coverage == 'hour':
                coverage = timedelta(hour=1)
            elif coverage == 'day':
                coverage = timedelta(days=1)
            elif coverage == 'year':
                coverage = timedelta(year=1)
            mode = dlg.modeComboBox.GetValue()
            #print "Stream: ", len(self.stream), len(self.plotstream)
            #print "Data: ", self.stream[0].time, self.stream[-1].time, self.plotstream[0].time, self.plotstream[-1].time
            #print "Main : ", dateformat, fileformat, coverage, mode
            try:
                self.plotstream.write(path,
                                filenamebegins=filenamebegins,
                                filenameends=filenameends,
                                dateformat=dateformat,
                                mode=mode,
                                coverage=coverage,
                                format_type=fileformat)
            except:
                self.menu_p.rep_page.logMsg("Writing failed - Permission?")
        dlg.Destroy()

    def _db_connect(self, host, user, passwd, dbname):
        try:
            self.db.close()
        except:
            pass
        try:
            self.db = MySQLdb.connect (host=host,user=user,passwd=passwd,db=dbname)
        except:
            self.db = False
        if self.db:
            self.DBOpen.Enable(True)
            self.menu_p.rep_page.logMsg('- MySQL Database selected.')
            self.changeStatusbar("Database %s successfully connected" % (dbname))
        else:
            self.menu_p.rep_page.logMsg('- MySQL Database access failed.')
            self.changeStatusbar("Database connection failed")

    def OnDBConnect(self, event):
        """
        Provide access for local network:
        Open your /etc/mysql/my.cnf file in your editor.
        scroll down to the entry:
        bind-address = 127.0.0.1
        and you can either hash that so it binds to all ip addresses assigned
        #bind-address = 127.0.0.1
        or you can specify an ipaddress to bind to. If your server is using dhcp then just hash it out.
        Then you'll need to create a user that is allowed to connect to your database of choice from the host/ip your connecting from.
        Login to your mysql console:
        milkchunk@milkchunk-desktop:~$ mysql -uroot -p
        GRANT ALL PRIVILEGES ON *.* TO 'user'@'%' IDENTIFIED BY 'some_pass' WITH GRANT OPTION;
        You change out the 'user' to whatever user your wanting to use and the '%' is a hostname wildcard. Meaning that you can connect from any hostname with it. You can change it to either specify a hostname or just use the wildcard.
        Then issue the following:
        FLUSH PRIVILEGES;
        Be sure to restart your mysql (because of the config file editing):
        /etc/init.d/mysql restart
        """
        dlg = DatabaseConnectDialog(None, title='MySQL Database: Connect to')
        dlg.hostTextCtrl.SetValue(self.host)
        dlg.userTextCtrl.SetValue(self.user)
        dlg.passwdTextCtrl.SetValue(self.passwd)
        if self.db == None or self.db == 'None' or not self.db:
            dlg.dbTextCtrl.SetValue('None')
        else:
            dlg.dbTextCtrl.SetValue(self.dbname)
        if dlg.ShowModal() == wx.ID_OK:
            self.host = dlg.hostTextCtrl.GetValue()
            self.user = dlg.userTextCtrl.GetValue()
            self.passwd = dlg.passwdTextCtrl.GetValue()
            self.dbname = dlg.dbTextCtrl.GetValue()
            self._db_connect(self.host, self.user, self.passwd, self.dbname)
            """
            self.db = MySQLdb.connect (host=host,user=user,passwd=passwd,db=mydb)
            if self.db:
                self.DBOpen.Enable(True)
                self.menu_p.rep_page.logMsg('- MySQL Database selected.')
                self.changeStatusbar("Database %s successfully connected" % (self.db))
            else:
                self.menu_p.rep_page.logMsg('- MySQL Database access failed.')
                self.changeStatusbar("Database connection failed")
            """
        dlg.Destroy()

    def OnFileQuit(self, event):
        self.Close()


    def OnSave(self, event):
        textfile = open(os.path.join(self.dirname, self.filename), 'w')
        textfile.write(self.control.GetValue())
        textfile.close()

    def OnSaveAs(self, event):
        if self.askUserForFilename(defaultFile=self.filename, style=wx.SAVE,
                                   **self.defaultFileDialogOptions()):
            self.OnSave(event)


    def OnOptionsInit(self, event):
        """
        DEFINITION
            Change options
        """
        dlg = OptionsInitDialog(None, title='Options: Parameter specifications')
        # database
        dlg.hostTextCtrl.SetValue(self.host)
        dlg.userTextCtrl.SetValue(self.user)
        dlg.passwdTextCtrl.SetValue(self.passwd)
        dlg.dbTextCtrl.SetValue(self.dbname)
        # database
        dlg.dirnameTextCtrl.SetValue(self.dirname)

        # default paths
        dlg.dipathlistTextCtrl.SetValue(self.dipathlist)
        dlg.divariopathTextCtrl.SetValue(self.divariopath)
        dlg.discalarpathTextCtrl.SetValue(self.discalarpath)

        # Default di parameter
        dlg.diexpDTextCtrl.SetValue(str(self.diexpD))
        dlg.diexpITextCtrl.SetValue(str(self.diexpI))
        dlg.dialphaTextCtrl.SetValue(str(self.dialpha))
        dlg.dideltaFTextCtrl.SetValue(str(self.dideltaF))

        dlg.ditypeTextCtrl.SetValue(self.ditype)
        dlg.stationidTextCtrl.SetValue(self.stationid)
        dlg.diidTextCtrl.SetValue(self.diid)
        dlg.diazimuthTextCtrl.SetValue(self.diazimuth)
        dlg.dipierTextCtrl.SetValue(self.dipier)
        dlg.didbaddTextCtrl.SetValue(self.didbadd)

        #dlg.hostTextCtrl.SetValue(self.compselect)
        #dlg.hostTextCtrl.SetValue(self.host)
        if dlg.ShowModal() == wx.ID_OK:
            host = dlg.hostTextCtrl.GetValue()
            user = dlg.userTextCtrl.GetValue()
            passwd = dlg.passwdTextCtrl.GetValue()
            db = dlg.dbTextCtrl.GetValue()
            if db == '':
                db = 'None'
            dirname=dlg.dirnameTextCtrl.GetValue()

            diexpD=float(dlg.diexpDTextCtrl.GetValue())
            diexpI=float(dlg.diexpITextCtrl.GetValue())
            dialpha=float(dlg.dialphaTextCtrl.GetValue())
            dideltaF=float(dlg.dideltaFTextCtrl.GetValue())
            ditype=dlg.ditypeTextCtrl.GetValue()
            dipathlist=dlg.dipathlistTextCtrl.GetValue()
            divariopath=dlg.divariopathTextCtrl.GetValue()
            discalarpath=dlg.discalarpathTextCtrl.GetValue()

            stationid=dlg.stationidTextCtrl.GetValue()
            diid=dlg.diidTextCtrl.GetValue()
            diazimuth=dlg.diazimuthTextCtrl.GetValue()
            dipier=dlg.dipierTextCtrl.GetValue()
            didbadd=dlg.didbaddTextCtrl.GetValue()

            basecompselect= 'spline' #basecompselect
            saveini(host=host, user=user, passwd=passwd, dbname=db, dirname=dirname, basecompselect=basecompselect,dipathlist=dipathlist, divariopath=divariopath, discalarpath=discalarpath, diexpD=diexpD, diexpI=diexpI, dialpha=dialpha, dideltaF=dideltaF, ditype=ditype,stationid=stationid, diid=diid, diazimuth=diazimuth, dipier=dipier, didbadd=didbadd)

            inipara = loadini()
            self.initParameter(inipara)

        dlg.Destroy()


    def OnOptionsObs(self, event):
        dlg = OptionsObsDialog(None, title='Options: Observatory specifications')
        dlg.ShowModal()
        dlg.Destroy()

        #dlg = wx.MessageDialog(self, "Coming soon:\n"
        #                "Modify observatory specifications\n",
        #                "PyMag by RL", wx.OK|wx.ICON_INFORMATION)
        #dlg.ShowModal()
        #dlg.Destroy()

    def onOpenAuxButton(self, event):
        if self.askUserForFilename(style=wx.OPEN,
                                   **self.defaultFileDialogOptions()):
            #dat = read_general(os.path.join(self.dirname, self.filename), 0)
            textfile = open(os.path.join(self.dirname, self.filename), 'r')
            self.menu_p.gen_page.AuxDataTextCtrl.SetValue(textfile.read())
            textfile.close()
            #print dat

    def changeStatusbar(self,msg):
        self.SetStatusText(msg)


    # ################
    # page methods:

    # pages: stream (plot, coordinate), analysis (smooth, filter, fit, baseline etc),
    #          specials(spectrum, power), absolutes (), report (log), monitor (access web socket)



    # ------------------------------------------------------------------------------------------
    # ################
    # Analysis functions
    # ################
    # ------------------------------------------------------------------------------------------

    def onFilterButton(self, event):
        """
        Method for filtering
        """
        self.changeStatusbar("Filtering...")

        # open dialog to modify filter parameters
        #keystr = self.menu_p.met_page.keysTextCtrl.GetValue().encode('ascii','ignore')
        #keys = keystr.split(',')
        sr = self.plotstream.samplingrate()

        filter_type = 'gaussian'
        resample_offset = 0.0
        if sr < 0.2: # use 1 second filter with 0.3 Hz cut off as default
                filter_width = timedelta(seconds=3.33333333)
                resample_period = 1.0
        elif sr < 50: # use 1 minute filter with 0.008 Hz cut off as default
                filter_width = timedelta(minutes=2)
                resample_period = 60.0
        else: # use 1 hour flat filter
                filter_width = timedelta(minutes=60)
                resample_period = 3600.0
                resample_offset = 1800.0
                filter_type = 'flat'
        miss = 'conservative'

        dlg = AnalysisFilterDialog(None, title='Analysis: Filter', samplingrate=sr, resample=True, winlen=filter_width.seconds, resint=resample_period, resoff= resample_offset, filtertype=filter_type)
        if dlg.ShowModal() == wx.ID_OK:
            filtertype = dlg.filtertypeComboBox.GetValue()
            filterlength = float(dlg.lengthTextCtrl.GetValue())
            resampleinterval = float(dlg.resampleTextCtrl.GetValue())
            resampleoffset = float(dlg.resampleoffsetTextCtrl.GetValue())
            missingdata = dlg.methodRadioBox.GetStringSelection()
            print (filtertype,filterlength,missingdata,resampleinterval,resampleoffset)
            if missingdata == 'IAGA':
                miss = 'mean'
            elif missingdata == 'interpolate':
                miss = 'interpolate'

            self.plotstream = self.plotstream.filter(keys=self.shownkeylist,filter_type=filtertype,filter_length=filterlength,resample_period=resampleinterval,resample_offset=resampleoffset,missingdata=miss,resample=True)
            self.menu_p.rep_page.logMsg('- data filtered: {} window, {} Hz passband'.format(filtertype,1./filterlength))

            self.ActivateControls(self.plotstream)
            self.OnPlot(self.plotstream,self.shownkeylist,padding=self.padding, specialdict=self.specialdict,errorbars=self.errorbars,colorlist=self.colorlist, symbollist=self.symbollist,annotate=self.annotate,stormphases=self.stormphases, t_stormphases=self.t_stormphases,includeid=self.includeid,function=self.function, plottype=self.plottype,labels=self.labels,resolution=self.resolution,confinex=self.confinex)
        self.changeStatusbar("Ready")


    def onDerivativeButton(self, event):
        """
        Method for derivative
        """
        self.changeStatusbar("Calculating derivative ...")
        keys = self.shownkeylist

        if len(self.plotstream.ndarray[0]) == 0:
            self.plotstream = self.stream.copy()

        self.menu_p.rep_page.logMsg("- calculating derivative")
        self.plotstream = self.plotstream.differentiate(keys=keys,put2keys=keys)

        self.menu_p.rep_page.logMsg('- derivative calculated')
        self.ActivateControls(self.plotstream)
        self.OnPlot(self.plotstream,self.shownkeylist,padding=self.padding, specialdict=self.specialdict,errorbars=self.errorbars,colorlist=self.colorlist, symbollist=self.symbollist,annotate=self.annotate,stormphases=self.stormphases, t_stormphases=self.t_stormphases,includeid=self.includeid,function=self.function, plottype=self.plottype,labels=self.labels,resolution=self.resolution,confinex=self.confinex)
        self.changeStatusbar("Ready")

    def onFitButton(self, event):
        """
        Method for fitting
        """
        self.changeStatusbar("Fitting ...")
        keys = self.shownkeylist
        if len(self.plotstream.ndarray[0]) == 0:
            self.plotstream = self.stream.copy()
        fitknots = str(0.5)
        fitdegree = str(4)
        fitfunc='spline'
        dlg = AnalysisFitDialog(None, title='Analysis: Fit parameter', fitfunc=fitfunc, fitknots=fitknots, fitdegree=fitdegree)
        if dlg.ShowModal() == wx.ID_OK:
            fitfunc = dlg.funcComboBox.GetValue()
            knots = dlg.knotsTextCtrl.GetValue()
            degree = dlg.degreeTextCtrl.GetValue()
            self.menu_p.rep_page.logMsg('Fitting with %s, %s, %s' % (fitfunc, knots, degree))
            if not 0<float(knots)<1:
                knots = 0.5
            if not degree>0:
                degree = 1
            else:
                degree = int(degree)
            if len(self.plotstream.ndarray[0]) > 0:
                func = self.plotstream.fit(keys=keys)
                self.function = func
                self.ActivateControls(self.plotstream)
                self.OnPlot(self.plotstream,self.shownkeylist,padding=self.padding, specialdict=self.specialdict,errorbars=self.errorbars,colorlist=self.colorlist, symbollist=self.symbollist,annotate=self.annotate,stormphases=self.stormphases, t_stormphases=self.t_stormphases,includeid=self.includeid,function=self.function, plottype=self.plottype,labels=self.labels,resolution=self.resolution,confinex=self.confinex)
            else:
                # Msgbox to load data first
                pass

        dlg.Destroy()
        self.menu_p.rep_page.logMsg('- data fitted')
        self.changeStatusbar("Ready")


    def onOffsetButton(self, event):
        """
        Method for offset correction
        """
        self.changeStatusbar("Adding offsets ...")
        keys = self.shownkeylist
        offsetdict = {}

        # get currently zoomed time limits and use as timerange
        self.xlimits = self.plot_p.xlimits
        if not self.xlimits:
            self.xlimits = [num2date(self.plotstream.ndarray[0][0]),num2date(self.plotstream.ndarray[0][-1])]
        else:
            self.xlimits = [num2date(self.xlimits[0]),num2date(self.xlimits[-1])]

        dlg = AnalysisOffsetDialog(None, title='Analysis: define offsets', keylst=keys, xlimits=self.xlimits)
        if dlg.ShowModal() == wx.ID_OK:
            for key in keys:
                offset = eval('dlg.'+key+'TextCtrl.GetValue()')
                if not offset in ['','0']:
                    if not float(offset) == 0:
                        offsetdict[key] = float(offset)
            val = dlg.offsetRadioBox.GetStringSelection()
            print ("Offset", val)
            if str(val) == 'all':
                toffset = dlg.timeshiftTextCtrl.GetValue()
                if not float(toffset) == 0:
                    offsetdict['time'] = timedelta(seconds=float(toffset))
                self.plotstream = self.plotstream.offset(offsetdict)
            else:
                stday = dlg.StartDatePicker.GetValue()
                sttime = str(dlg.StartTimeTextCtrl.GetValue())
                sd = datetime.strftime(datetime.fromtimestamp(stday.GetTicks()), "%Y-%m-%d")
                st= datetime.strptime(str(sd)+'_'+sttime, "%Y-%m-%d_%H:%M:%S")
                edday = dlg.EndDatePicker.GetValue()
                edtime = str(dlg.EndTimeTextCtrl.GetValue())
                ed = datetime.strftime(datetime.fromtimestamp(edday.GetTicks()), "%Y-%m-%d")
                et= datetime.strptime(str(ed)+'_'+edtime, "%Y-%m-%d_%H:%M:%S")
                self.plotstream = self.plotstream.offset(offsetdict, starttime=st, endtime=et)

            self.ActivateControls(self.plotstream)
            self.OnPlot(self.plotstream,self.shownkeylist,padding=self.padding, specialdict=self.specialdict,errorbars=self.errorbars,colorlist=self.colorlist, symbollist=self.symbollist,annotate=self.annotate,stormphases=self.stormphases, t_stormphases=self.t_stormphases,includeid=self.includeid,function=self.function, plottype=self.plottype,labels=self.labels,resolution=self.resolution,confinex=self.confinex)

        dlg.Destroy()
        self.changeStatusbar("Ready")

    def onActivityButton(self, event):
        """
        Method for offset correction
        """
        self.changeStatusbar("Getting activity (FMI method)...")

        keys = self.shownkeylist
        offsetdict = {}

        #dlg = AnalysisActivityDialog(None, title='Analysis: get k values (FMI)')
        #if dlg.ShowModal() == wx.ID_OK:
        self.plotstream = self.plotstream.k_fmi()
        if len(self.plotstream.ndarray[0]) > 0:
            self.ActivateControls(self.plotstream)
            self.OnPlot(self.plotstream,self.shownkeylist,padding=self.padding, specialdict=self.specialdict,errorbars=self.errorbars,colorlist=self.colorlist, symbollist=self.symbollist,annotate=self.annotate,stormphases=self.stormphases, t_stormphases=self.t_stormphases,includeid=self.includeid,function=self.function, plottype=self.plottype,labels=self.labels,resolution=self.resolution,confinex=self.confinex)

        dlg.Destroy()
        self.changeStatusbar("Ready")

    def onRotationButton(self, event):
        """
        Method for offset correction
        """
        self.changeStatusbar("Rotating data ...")

        if len(self.plotstream.ndarray[0]) > 0:
            # XXX Eventually SetValues from init
            dlg = AnalysisRotationDialog(None, title='Analysis: rotate data')
            if dlg.ShowModal() == wx.ID_OK:
                alphat = dlg.alphaTextCtrl.GetValue()
                betat = dlg.betaTextCtrl.GetValue()
                try:
                    alpha = float(alphat)
                except:
                    alpha = 0.0
                try:
                    beta = float(betat)
                except:
                    beta = 0.0

                self.plotstream = self.plotstream.rotation(alpha=alpha, beta=beta)
                self.menu_p.rep_page.logMsg('- rotated stream by alpha = %s and beta = %s' % (alphat,betat))
                self.ActivateControls(self.plotstream)
                self.OnPlot(self.plotstream,self.shownkeylist,padding=self.padding, specialdict=self.specialdict,errorbars=self.errorbars,colorlist=self.colorlist, symbollist=self.symbollist,annotate=self.annotate,stormphases=self.stormphases, t_stormphases=self.t_stormphases,includeid=self.includeid,function=self.function, plottype=self.plottype,labels=self.labels,resolution=self.resolution,confinex=self.confinex)

        dlg.Destroy()
        self.changeStatusbar("Ready")

    def onMeanButton(self, event):
        """
        DESCRIPTION
             Calculates means values for all keys of shownkeylist
        """
        self.changeStatusbar("Calculating means ...")
        keys = self.shownkeylist
        meanfunc = 'mean'

        teststream = self.plotstream.copy()
        # limits
        self.xlimits = self.plot_p.xlimits
        if not self.xlimits == [self.plotstream.ndarray[0],self.plotstream.ndarray[-1]]:
            testarray = self.plotstream._select_timerange(starttime=self.xlimits[0],endtime=self.xlimits[1])
            teststream = DataStream([LineStruct()],self.plotstream.header,testarray)

        mean = [teststream.mean(key,meanfunction='mean',std=True,percentage=10) for key in keys] 
        t_limits = teststream._find_t_limits()
        trange = '- mean - timerange: {} to {}'.format(t_limits[0],t_limits[1])
        self.menu_p.rep_page.logMsg(trange)
        for idx,me in enumerate(mean):
            meanline = '- mean - key: {} = {} +/- {}'.format(keys[idx],me[0],me[1])
            self.menu_p.rep_page.logMsg(meanline)
            trange = trange + '\n' + meanline
        # open message dialog
        dlg = wx.MessageDialog(self, "Means:\n"+
                        str(trange),
                        "Analysis: Mean values", wx.OK|wx.ICON_INFORMATION)
        dlg.ShowModal()
        dlg.Destroy()
        self.changeStatusbar("Ready")

    def onMaxButton(self, event):
        """
        DESCRIPTION
             Calculates max values for all keys of shownkeylist
        """
        self.changeStatusbar("Calculating maxima ...")
        keys = self.shownkeylist

        teststream = self.plotstream.copy()
        # limits
        self.xlimits = self.plot_p.xlimits
        if not self.xlimits == [self.plotstream.ndarray[0],self.plotstream.ndarray[-1]]:
            testarray = self.plotstream._select_timerange(starttime=self.xlimits[0],endtime=self.xlimits[1])
            teststream = DataStream([LineStruct()],self.plotstream.header,testarray)

        maxi = [teststream._get_max(key,returntime=True) for key in keys] 
        t_limits = teststream._find_t_limits()
        trange = '- maxima - timerange: {} to {}'.format(t_limits[0],t_limits[1])
        self.menu_p.rep_page.logMsg(trange)
        for idx,me in enumerate(maxi):
            meanline = '- maxima - key: {} = {} at {}'.format(keys[idx],me[0],num2date(me[1]))
            self.menu_p.rep_page.logMsg(meanline)
            trange = trange + '\n' + meanline
        # open message dialog
        dlg = wx.MessageDialog(self, "Maxima:\n"+
                        str(trange),
                        "Analysis: Maximum values", wx.OK|wx.ICON_INFORMATION)
        dlg.ShowModal()
        dlg.Destroy()
        self.changeStatusbar("Ready")

    def onMinButton(self, event):
        """
        DESCRIPTION
             Calculates means values for all keys of shownkeylist
        """
        self.changeStatusbar("Calculating minima ...")
        keys = self.shownkeylist

        teststream = self.plotstream.copy()
        # limits
        self.xlimits = self.plot_p.xlimits
        if not self.xlimits == [self.plotstream.ndarray[0],self.plotstream.ndarray[-1]]:
            testarray = self.plotstream._select_timerange(starttime=self.xlimits[0],endtime=self.xlimits[1])
            teststream = DataStream([LineStruct()],self.plotstream.header,testarray)

        mini = [teststream._get_min(key,returntime=True) for key in keys] 
        t_limits = teststream._find_t_limits()
        trange = '- minima - timerange: {} to {}'.format(t_limits[0],t_limits[1])
        self.menu_p.rep_page.logMsg(trange)
        for idx,me in enumerate(mini):
            meanline = '- minima - key: {} = {} at {}'.format(keys[idx],me[0],num2date(me[1]))
            self.menu_p.rep_page.logMsg(meanline)
            trange = trange + '\n' + meanline
        # open message dialog
        dlg = wx.MessageDialog(self, "Minima:\n"+
                        str(trange),
                        "Analysis: Minimum values", wx.OK|wx.ICON_INFORMATION)
        dlg.ShowModal()
        dlg.Destroy()
        self.changeStatusbar("Ready")

    def onSmoothButton(self, event):
        """
        DESCRIPTION
             Calculates smoothed curve
        """
        self.changeStatusbar("Smoothing ... be patient")
        sr = self.plotstream.samplingrate()

        filter_type = 'gaussian'
        resample_offset = 0.0
        if sr < 0.2: # use 1 second filter with 0.3 Hz cut off as default
                filter_width = timedelta(seconds=3.33333333)
                resample_period = 1.0
        elif sr < 50: # use 1 minute filter with 0.008 Hz cut off as default
                filter_width = timedelta(minutes=2)
                resample_period = 60.0
        else: # use 1 hour flat filter
                filter_width = timedelta(minutes=60)
                resample_period = 3600.0
                resample_offset = 1800.0
                filter_type = 'flat'
        miss = 'conservative'

        dlg = AnalysisFilterDialog(None, title='Analysis: Filter', samplingrate=sr, resample=False, winlen=filter_width.seconds, resint=resample_period, resoff= resample_offset, filtertype=filter_type)
        if dlg.ShowModal() == wx.ID_OK:
            filtertype = dlg.filtertypeComboBox.GetValue()
            filterlength = float(dlg.lengthTextCtrl.GetValue())
            missingdata = dlg.methodRadioBox.GetStringSelection()
            if missingdata == 'IAGA':
                miss = 'mean'
            elif missingdata == 'interpolate':
                miss = 'interpolate'

            self.plotstream = self.plotstream.filter(keys=self.shownkeylist,filter_type=filtertype,filter_length=filterlength,missingdata=miss,noresample=True)
            self.menu_p.rep_page.logMsg('- data filtered: {} window, {} Hz passband'.format(filtertype,1./filterlength))

            self.ActivateControls(self.plotstream)
            self.OnPlot(self.plotstream,self.shownkeylist,padding=self.padding, specialdict=self.specialdict,errorbars=self.errorbars,colorlist=self.colorlist, symbollist=self.symbollist,annotate=self.annotate,stormphases=self.stormphases, t_stormphases=self.t_stormphases,includeid=self.includeid,function=self.function, plottype=self.plottype,labels=self.labels,resolution=self.resolution,confinex=self.confinex)
        self.changeStatusbar("Ready")

    def onBaselineButton(self, event):
        """
        DESCRIPTION
             Calculates baseline correction
        """
        self.changeStatusbar("Baseline adoption ...")
        keys = self.shownkeylist
        self.changeStatusbar("Ready")

    def onDeltafButton(self, event):
        """
        DESCRIPTION
             Calculates delta F values
        """
        self.changeStatusbar("Delta F ...")

        self.plotstream = self.plotstream.delta_f()
        print (self.plotstream._get_key_headers())
        #if 'df' in self.plotstream._get_key_headers() and not 'df' in self.shownkeylist:
        #    self.shownkeylist.append('df')
        self.menu_p.rep_page.logMsg('- determined delta F between x,y,z and f')
        self.ActivateControls(self.plotstream)
        self.OnPlot(self.plotstream,self.shownkeylist,padding=self.padding, specialdict=self.specialdict,errorbars=self.errorbars,colorlist=self.colorlist, symbollist=self.symbollist,annotate=self.annotate,stormphases=self.stormphases, t_stormphases=self.t_stormphases,includeid=self.includeid,function=self.function, plottype=self.plottype,labels=self.labels,resolution=self.resolution,confinex=self.confinex)
        self.changeStatusbar("Ready")

    def onMergeButton(self, event):
        """
        DESCRIPTION
             Merges two streams
        """
        self.changeStatusbar("Merging ...")
        keys = self.shownkeylist
        self.changeStatusbar("Ready")

    def onSubtractButton(self, event):
        """
        DESCRIPTION
             Subtracts two stream
        """
        self.changeStatusbar("Subtracting ...")
        keys = self.shownkeylist
        self.changeStatusbar("Ready")

    def onStackButton(self, event):
        """
        DESCRIPTION
             Stacking/Averaging streams
        """
        self.changeStatusbar("Stacking/Averaging streams ...")
        keys = self.shownkeylist
        self.changeStatusbar("Ready")

    # ------------------------------------------------------------------------------------------
    # ################
    # Stream page functions
    # ################
    # ------------------------------------------------------------------------------------------

    def onErrorBarCheckBox(self,event):
        """
        DESCRIPTION
            Switch display of error bars.
        RETURNS
            kwarg for OnPlot method
        """

        if not self.menu_p.str_page.errorBarsCheckBox.GetValue():
            self.errorbars=False
            self.menu_p.str_page.errorBarsCheckBox.SetValue(False)
        else:
            self.errorbars=True
            self.menu_p.str_page.errorBarsCheckBox.SetValue(True)
        self.ActivateControls(self.plotstream)
        if self.plotstream.length()[0] > 0:
            self.OnPlot(self.plotstream,self.shownkeylist,padding=self.padding, specialdict=self.specialdict,errorbars=self.errorbars,colorlist=self.colorlist, symbollist=self.symbollist,annotate=self.annotate,stormphases=self.stormphases, t_stormphases=self.t_stormphases,includeid=self.includeid,function=self.function, plottype=self.plottype,labels=self.labels,resolution=self.resolution,confinex=self.confinex)
            self.changeStatusbar("Ready")
        else:
            self.changeStatusbar("Failure")
        

    def onConfinexCheckBox(self,event):
        """
        DESCRIPTION
            Switch display of error bars.
        RETURNS
            kwarg for OnPlot method
        """
        if not self.menu_p.str_page.confinexCheckBox.GetValue():
            self.confinex=False
            self.menu_p.str_page.confinexCheckBox.SetValue(False)
        else:
            self.confinex=True
            self.menu_p.str_page.confinexCheckBox.SetValue(True)
        self.ActivateControls(self.plotstream)
        if self.plotstream.length()[0] > 0:
            self.OnPlot(self.plotstream,self.shownkeylist,padding=self.padding, specialdict=self.specialdict,errorbars=self.errorbars,colorlist=self.colorlist, symbollist=self.symbollist,annotate=self.annotate,stormphases=self.stormphases, t_stormphases=self.t_stormphases,includeid=self.includeid,function=self.function, plottype=self.plottype,labels=self.labels,resolution=self.resolution,confinex=self.confinex)
            self.changeStatusbar("Ready")
        else:
            self.changeStatusbar("Failure")


    def onTrimStreamButton(self,event):
        """
        DESCRIPTION
        """
        stday = self.menu_p.str_page.startDatePicker.GetValue()
        sttime = str(self.menu_p.str_page.startTimePicker.GetValue())
        sd = datetime.strftime(datetime.fromtimestamp(stday.GetTicks()), "%Y-%m-%d")
        start= datetime.strptime(str(sd)+'_'+sttime, "%Y-%m-%d_%H:%M:%S")
        enday = self.menu_p.str_page.endDatePicker.GetValue()
        entime = str(self.menu_p.str_page.endTimePicker.GetValue())
        ed = datetime.strftime(datetime.fromtimestamp(enday.GetTicks()), "%Y-%m-%d")
        end= datetime.strptime(ed+'_'+entime, "%Y-%m-%d_%H:%M:%S")

        try:
            self.changeStatusbar("Trimming stream ...")
            newarray = self.plotstream._select_timerange(starttime=start, endtime=end)
            self.plotstream=DataStream([LineStruct()],self.plotstream.header,newarray)
            self.menu_p.rep_page.logMsg('- Stream trimmed: {} to {}'.format(start,end))
        except:
            self.menu_p.rep_page.logMsg('- Trimming failed')

        self.ActivateControls(self.plotstream)
        if self.plotstream.length()[0] > 0:
            self.OnPlot(self.plotstream,self.shownkeylist,padding=self.padding, specialdict=self.specialdict,errorbars=self.errorbars,colorlist=self.colorlist, symbollist=self.symbollist,annotate=self.annotate,stormphases=self.stormphases, t_stormphases=self.t_stormphases,includeid=self.includeid,function=self.function, plottype=self.plottype,labels=self.labels,resolution=self.resolution,confinex=self.confinex)
            self.changeStatusbar("Ready")
        else:
            self.changeStatusbar("Failure")


    def openStream(self,path='',mintime=None,maxtime=None,extension=None):
        # TODO Move this method to section File menu
        """
        DESCRIPTION:
            Opens time range dialog and loads data. Returns stream.
        USED BY:
            OnOpenDir and OnOpenDB
        """
        dlg = LoadDataDialog(None, title='Select timerange:',mintime=mintime,maxtime=maxtime, extension=extension)
        if dlg.ShowModal() == wx.ID_OK:
            stday = dlg.startDatePicker.GetValue()
            sttime = dlg.startTimePicker.GetValue()
            enday = dlg.endDatePicker.GetValue()
            entime = dlg.startTimePicker.GetValue()
            ext = dlg.fileExt.GetValue()

            sd = datetime.fromtimestamp(stday.GetTicks())
            ed = datetime.fromtimestamp(enday.GetTicks())
            st = datetime.strftime(sd, "%Y-%m-%d") + " " + sttime
            start = datetime.strptime(st, "%Y-%m-%d %H:%M:%S")
            et = datetime.strftime(ed, "%Y-%m-%d") + " " + entime
            end = datetime.strptime(et, "%Y-%m-%d %H:%M:%S")

        if isinstance(path, basestring):
            if not path=='':
                self.menu_p.str_page.fileTextCtrl.SetValue(ext)
                stream = read(path_or_url=os.path.join(path,ext), starttime=start, endtime=end)
        else:
            # assume Database
            try:
                stream = readDB(path[0],path[1], starttime=start, endtime=end)
            except:
                print ("Reading failed")

        return stream

    """
    def onOpenStreamButton(self, event):
        # TODO Remove this method
        stream = DataStream()
        stday = self.menu_p.str_page.startDatePicker.GetValue()
        sttime = self.menu_p.str_page.startTimePicker.GetValue()
        sd = datetime.fromtimestamp(stday.GetTicks())
        enday = self.menu_p.str_page.endDatePicker.GetValue()
        ed = datetime.fromtimestamp(enday.GetTicks())
        path = self.menu_p.str_page.pathTextCtrl.GetValue()
        files = self.menu_p.str_page.fileTextCtrl.GetValue()


        if path == "":
            dlg = wx.MessageDialog(self, "Please select a path first!\n"
                        "go to File -> Select Dir\n",
                        "OpenStream", wx.OK|wx.ICON_INFORMATION)
            dlg.ShowModal()
            dlg.Destroy()
            return
        if files == "":
            dlg = wx.MessageDialog(self, "Please select a file first!\n"
                        "accepted wildcards are * (e.g. *, *.dat, FGE*)\n",
                        "OpenStream", wx.OK|wx.ICON_INFORMATION)
            dlg.ShowModal()
            dlg.Destroy()
            return

        start= datetime.strftime(sd, "%Y-%m-%d %H:%M:%S")
        end= datetime.strftime(ed, "%Y-%m-%d %H:%M:%S")


        try:
            self.changeStatusbar("Loading data ...")
            if path.endswith('/'):
                address = path
                stream = read(path_or_url=address,starttime=sd, endtime=ed)
            elif path.startswith('MySQL'):
                start= datetime.strftime(sd, "%Y-%m-%d %H:%M:%S")
                end= datetime.strftime(ed, "%Y-%m-%d %H:%M:%S")
                stream = readDB(self.db, files, starttime=sd, endtime=ed)
            else:
                address = os.path.join(path,files)
                stream = read(path_or_url=address,starttime=sd, endtime=ed)
            self.UpdateTimeRanges(stream)
        except:
            dlg = wx.MessageDialog(self, "Could not read file(s)!\n"
                        "check your files and/or selected time range\n",
                        "OpenStream", wx.OK|wx.ICON_INFORMATION)
            dlg.ShowModal()
            dlg.Destroy()
            return

        self.menu_p.rep_page.logMsg('- Stream loaded of length %i' % len(stream))

        if self.CheckStreamContent(stream):
            self.OnInitialPlot(stream)
    """

    """
    def onReDrawButton(self, event):
        # TODO Remove this method

        #self.plotstream = self.stream.copy()
        print("Stream restored of length ", len(self.stream.ndarray[0]))
        #self.SetPageValues(self.stream)
        #self.menu_p.str_page.lengthStreamTextCtrl.SetValue(str(len(stream)))
        if self.CheckStreamContent(self.stream):
            self.stream.header = self.orgheader
            self.OnInitialPlot(self.stream)
        stday = self.menu_p.str_page.startDatePicker.GetValue()
        sttime = self.menu_p.str_page.startTimePicker.GetValue()
        sd = datetime.fromtimestamp(stday.GetTicks())
        enday = self.menu_p.str_page.endDatePicker.GetValue()
        entime = self.menu_p.str_page.endTimePicker.GetValue()
        ed = datetime.fromtimestamp(enday.GetTicks())
        print("OnReDraw",sttime)

        if 'AM' in sttime or 'PM' in sttime:
            stt = datetime.strptime(sttime,'%I:%M:%S %p')
            ett = datetime.strptime(entime,'%I:%M:%S %p')
        else:
            stt = datetime.strptime(sttime,'%H:%M:%S')
            ett = datetime.strptime(entime,'%H:%M:%S')

        start = datetime.combine(datetime.date(sd), datetime.time(stt))
        end = datetime.combine(datetime.date(ed), datetime.time(ett))

        if len(self.stream) == 0:
            dlg = wx.MessageDialog(self, "Please select a path first!\n"
                        "go to File -> Select Dir\n",
                        "OpenStream", wx.OK|wx.ICON_INFORMATION)
            dlg.ShowModal()
            dlg.Destroy()
            return

        if len(self.plotstream.ndarray[0]) == 0:
            self.plotstream = self.stream.copy()

        #st = datetime.strftime(sd, "%Y-%m-%d") + " " + sttime
        #start = datetime.strptime(st, "%Y-%m-%d %H:%M:%S")
        #et = datetime.strftime(ed, "%Y-%m-%d") + " " + entime
        #end = datetime.strptime(et, "%Y-%m-%d %H:%M:%S")

        try:
            self.changeStatusbar("Loading data ...")
            stream = self.plotstream.trim(starttime=start, endtime=end)
            mintime = stream._get_min('time')
            maxtime = stream._get_max('time')
            self.menu_p.str_page.startDatePicker.SetValue(wx.DateTimeFromTimeT(time.mktime(num2date(mintime).timetuple())))
            self.menu_p.str_page.endDatePicker.SetValue(wx.DateTimeFromTimeT(time.mktime(num2date(maxtime).timetuple())))
            self.menu_p.str_page.startTimePicker.SetValue(num2date(mintime).strftime('%X'))
            self.menu_p.str_page.endTimePicker.SetValue(num2date(maxtime).strftime('%X'))
            #self.menu_p.str_page.startDatePicker.Disable()
            #self.menu_p.str_page.endDatePicker.Disable()
            #self.menu_p.str_page.startTimePicker.Disable()
            #self.menu_p.str_page.endTimePicker.Disable()
            self.menu_p.str_page.openStreamButton.Disable()
        except:
            dlg = wx.MessageDialog(self, "Could not trim data!\n"
                        "check your files and/or selected time range\n",
                        "OpenStream", wx.OK|wx.ICON_INFORMATION)
            dlg.ShowModal()
            dlg.Destroy()
            return

        print("Stream loaded of length ", len(stream))
        self.plotstream = stream.copy()
        self.SetPageValues(stream)
        #self.menu_p.str_page.lengthStreamTextCtrl.SetValue(str(len(stream)))
        self.OnInitialPlot(stream)
    """

    def onSelectKeys(self,event):
        """
        DESCRIPTION
            open dialog to select shown keys (check boxes)
        """

        if len(self.plotstream.ndarray[0]) == 0:
            self.plotstream = self.stream.copy()
        keylist = self.plotstream._get_key_headers(numerical=True)
        self.keylist = keylist
        shownkeylist = self.shownkeylist

        namelist = []
        unitlist = []
        for key in keylist:
            if not len(self.plotstream.ndarray[KEYLIST.index(key)]) == 0:
                value = self.plotstream.header.get('col-'+key)
                unit = self.plotstream.header.get('unit-col-'+key)
                if not value == '':
                    namelist.append(value)
                else:
                    namelist.append(key)
                if not unit == '':
                    unitlist.append(unit)
                else:
                    unitlist.append('')
        
        if len(self.plotstream.ndarray[0]) > 0:
            dlg = StreamSelectKeysDialog(None, title='Select keys:',keylst=keylist,shownkeys=self.shownkeylist,namelist=namelist)
            for elem in shownkeylist:
                exec('dlg.'+elem+'CheckBox.SetValue(True)')
            if dlg.ShowModal() == wx.ID_OK:
                shownkeylist = []
                for elem in keylist:
                    boolval = eval('dlg.'+elem+'CheckBox.GetValue()')
                    if boolval:
                        shownkeylist.append(elem)
                if len(shownkeylist) == 0:
                    shownkeylist = self.shownkeylist
                else:
                    self.shownkeylist = shownkeylist
                self.symbollist = [self.symbollist[0]]*len(shownkeylist)
                self.ActivateControls(self.plotstream)
                self.OnPlot(self.plotstream,self.shownkeylist,padding=self.padding, specialdict=self.specialdict,errorbars=self.errorbars,colorlist=self.colorlist, symbollist=self.symbollist,annotate=self.annotate,stormphases=self.stormphases, t_stormphases=self.t_stormphases,includeid=self.includeid,function=self.function, plottype=self.plottype,labels=self.labels,resolution=self.resolution,confinex=self.confinex)
                self.changeStatusbar("Ready")
            dlg.Destroy()
        else:
            self.changeStatusbar("Failure")


    def onExtractData(self,event):
        """
        DESCRIPTION:
            open dialog to choose extract parameter (paramater compare value)
            up to three possibilities
        """

        if len(self.plotstream.ndarray[0]) == 0:
            self.plotstream = self.stream.copy()
        keylist = self.shownkeylist
        if len(self.plotstream.ndarray[0]) > 0:
            dlg = StreamExtractValuesDialog(None, title='Extract:',keylst=keylist)
            if dlg.ShowModal() == wx.ID_OK:
                key1 = dlg.key1ComboBox.GetValue()
                comp1 = dlg.compare1ComboBox.GetValue()
                val1 = dlg.value1TextCtrl.GetValue()
                logic2 = dlg.logic2ComboBox.GetValue()
                logic3 = dlg.logic3ComboBox.GetValue()
                extractedstream = self.plotstream.extract(key1,val1,comp1)
                val2 = dlg.value2TextCtrl.GetValue()
                if not val2 == '':
                    key2 = dlg.key2ComboBox.GetValue()
                    comp2 = dlg.compare2ComboBox.GetValue()
                    if logic2 == 'and':
                        extractedstream = extractedstream.extract(key2,val2,comp2)
                    else:
                        extractedstream2 = self.plotstream.extract(key2,val2,comp2)
                        # TODO extractedstream = join(extractedstream,extractedstream2)
                    val3 = dlg.value3TextCtrl.GetValue()
                    if not val3 == '':
                        key3 = dlg.key3ComboBox.GetValue()
                        comp3 = dlg.compare3ComboBox.GetValue()
                        if logic3 == 'and':
                            extractedstream = extractedstream.extract(key3,val3,comp3)
                        else:
                            extractedstream3 = self.plotstream.extract(key3,val3,comp3)
                            # TODO extractedstream = join(extractedstream,extractedstream3)
                self.plotstream = extractedstream
                self.ActivateControls(self.plotstream)
                self.OnPlot(self.plotstream,self.shownkeylist,padding=self.padding, specialdict=self.specialdict,errorbars=self.errorbars,colorlist=self.colorlist, symbollist=self.symbollist,annotate=self.annotate,stormphases=self.stormphases, t_stormphases=self.t_stormphases,includeid=self.includeid,function=self.function, plottype=self.plottype,labels=self.labels,resolution=self.resolution,confinex=self.confinex)
                self.changeStatusbar("Ready")
        else:
            self.menu_p.rep_page.logMsg("Extract: No data available so far")
        # specify filters -> allow to define filters Combo with key - Combo with selector (>,<,=) - TextBox with Filter


    def onChangePlotOptions(self,event):
        """
        DESCRIPTION:
            open dialog to modify plot options (general (e.g. bgcolor) and  key
            specific (key: symbol color errorbar etc)
        """

        if len(self.plotstream.ndarray[0]) > 0:
            dlg = StreamPlotOptionsDialog(None, title='Plot Options:',optdict=self.plotopt)
            if dlg.ShowModal() == wx.ID_OK:
                for elem in self.plotopt:
                    val = eval('dlg.'+elem+'TextCtrl.GetValue()')
                    if not val == self.plotopt[elem]:
                        self.plotopt[elem] = val


    def onRestoreData(self,event):
        """
        Restore originally loaded data
        """
        self.flaglist = []

        if not len(self.stream.ndarray[0]) > 0:
            self.DeactivateAllControls()
            self.changeStatusbar("No data available")
            return False
        self.plotstream = self.stream.copy()
        self.plotstream.header = self.headerlist[self.currentstreamindex]

        self.menu_p.rep_page.logMsg('Original data restored...')
        self.InitPlotParameter()
        self.ActivateControls(self.stream)
        self.OnInitialPlot(self.stream)

    def onDailyMeansButton(self,event):
        """
        Restore originally loaded data
        """
        if self.plotstream.header.get('DataFormat') == 'MagPyDI':
            keys=['dx','dy','dz']
        else:
            keys = False
        self.plotstream = self.plotstream.dailymeans(keys)
        self.shownkeylist = self.plotstream._get_key_headers(numerical=True)[:3]
        self.symbollist = self.symbollist[0]*len(self.shownkeylist)

        self.ActivateControls(self.plotstream)
        self.errorbars = True
        self.OnPlot(self.plotstream,self.shownkeylist,padding=self.padding, specialdict=self.specialdict,errorbars=self.errorbars,colorlist=self.colorlist, symbollist=self.symbollist,annotate=self.annotate,stormphases=self.stormphases, t_stormphases=self.t_stormphases,includeid=self.includeid,function=self.function, plottype=self.plottype,labels=self.labels,resolution=self.resolution,confinex=self.confinex)
        self.menu_p.str_page.errorBarsCheckBox.SetValue(True)
        self.menu_p.str_page.errorBarsCheckBox.Enable()
        self.changeStatusbar("Ready")


    def onApplyBCButton(self,event):
        """
        Apply baselinecorrection
        """
        self.plotstream = self.plotstream.bc()
        self.ActivateControls(self.plotstream)
        self.OnPlot(self.plotstream,self.shownkeylist,padding=self.padding, specialdict=self.specialdict,errorbars=self.errorbars,colorlist=self.colorlist, symbollist=self.symbollist,annotate=self.annotate,stormphases=self.stormphases, t_stormphases=self.t_stormphases,includeid=self.includeid,function=self.function, plottype=self.plottype,labels=self.labels,resolution=self.resolution,confinex=self.confinex)


    def onAnnotateCheckBox(self,event):
        """
        Restore originally loaded data
        """
        #### get True or False
        if not self.menu_p.str_page.annotateCheckBox.GetValue():
            self.annotate=False
            self.menu_p.str_page.annotateCheckBox.SetValue(False)
        else:
            self.annotate=True
            self.menu_p.str_page.annotateCheckBox.SetValue(True)

        #mp.plot(self.plotstream,annotate=True)
        self.ActivateControls(self.plotstream)
        self.OnPlot(self.plotstream,self.shownkeylist,padding=self.padding, specialdict=self.specialdict,errorbars=self.errorbars,colorlist=self.colorlist, symbollist=self.symbollist,annotate=self.annotate,stormphases=self.stormphases, t_stormphases=self.t_stormphases,includeid=self.includeid,function=self.function, plottype=self.plottype,labels=self.labels,resolution=self.resolution,confinex=self.confinex)

    def onChangeComp(self, event):
        orgcomp = self.compselect
        self.compselect = self.menu_p.str_page.comp[event.GetInt()]
        coordinate = orgcomp+'2'+self.compselect
        self.changeStatusbar("Transforming ...")
        self.plotstream = self.plotstream._convertstream(coordinate)
        self.ActivateControls(self.plotstream)
        self.OnPlot(self.plotstream,self.shownkeylist,padding=self.padding, specialdict=self.specialdict,errorbars=self.errorbars,colorlist=self.colorlist, symbollist=self.symbollist,annotate=self.annotate,stormphases=self.stormphases, t_stormphases=self.t_stormphases,includeid=self.includeid,function=self.function, plottype=self.plottype,labels=self.labels,resolution=self.resolution,confinex=self.confinex)

    def onChangeSymbol(self, event):
        orgsymbol = self.symbolselect
        self.symbolselect = self.menu_p.str_page.symbol[event.GetInt()]
        self.changeStatusbar("Transforming ...")
        self.ActivateControls(self.plotstream)
        #if len(self.plotstream.ndarray[0]) == 0:
        #    self.plotstream = self.stream.copy()
        if self.symbolselect == 'line':
            self.symbollist = ['-' for elem in self.shownkeylist]
            self.OnPlot(self.plotstream,self.shownkeylist,padding=self.padding, specialdict=self.specialdict,errorbars=self.errorbars,colorlist=self.colorlist, symbollist=self.symbollist,annotate=self.annotate,stormphases=self.stormphases, t_stormphases=self.t_stormphases,includeid=self.includeid,function=self.function, plottype=self.plottype,labels=self.labels,resolution=self.resolution,confinex=self.confinex)
        elif self.symbolselect == 'point':
            self.symbollist = ['o' for elem in self.shownkeylist]
            self.OnPlot(self.plotstream,self.shownkeylist,padding=self.padding, specialdict=self.specialdict,errorbars=self.errorbars,colorlist=self.colorlist, symbollist=self.symbollist,annotate=self.annotate,stormphases=self.stormphases, t_stormphases=self.t_stormphases,includeid=self.includeid,function=self.function, plottype=self.plottype,labels=self.labels,resolution=self.resolution,confinex=self.confinex)
        self.changeStatusbar("Ready")


    def onFlagSelectionButton(self,event):
        """
        DESCRIPTION
            Restore originally loaded data
        """

        # Open external dialog with text control
        #prev_redir = sys.stdout
        #redir=RedirectText(self.menu_p.abs_page.dilogTextCtrl)
        #sys.stdout=redir
        ###   commands
        #sys.stdout=prev_redir

        self.changeStatusbar("Opening external data viewer ...")
        self.plot_p.plt.close()
        variables = self.keylist
        self.plotstream, flaglist = mp.plotFlag(self.plotstream,variables)
        self.flaglist.extend(flaglist)

        self.changeStatusbar("Updating plot ...")
        self.menu_p.rep_page.logMsg('- flagged user selection: added {} flags'.format(len(flaglist)))
        self.ActivateControls(self.plotstream)

        self.annotate = True
        self.menu_p.str_page.annotateCheckBox.SetValue(True)
        self.OnPlot(self.plotstream,self.shownkeylist,padding=self.padding, specialdict=self.specialdict,errorbars=self.errorbars,colorlist=self.colorlist, symbollist=self.symbollist,annotate=self.annotate,stormphases=self.stormphases, t_stormphases=self.t_stormphases,includeid=self.includeid,function=self.function, plottype=self.plottype,labels=self.labels,resolution=self.resolution,confinex=self.confinex)


    def onFlagOutlierButton(self, event):
        """
        DESCRIPTION
            Method for Outlier
        """
        self.changeStatusbar("Flagging outliers ...")
        sr = self.menu_p.met_page.samplingrateTextCtrl.GetValue().encode('ascii','ignore')
        keys = self.shownkeylist
        timerange = float(sr)*600.
        threshold=5.0

        # Open Dialog and return the parameters threshold, keys, timerange
        dlg = StreamFlagOutlierDialog(None, title='Stream: Flag outlier', threshold=threshold, timerange=timerange)
        if dlg.ShowModal() == wx.ID_OK:
            threshold = dlg.ThresholdTextCtrl.GetValue()
            timerange = dlg.TimerangeTextCtrl.GetValue()
        try:
            threshold = float(threshold)
            timerange = float(timerange)
            timerange = timedelta(seconds=timerange)
            flaglist = self.plotstream.flag_outlier(stdout=True,returnflaglist=True, keys=keys,threshold=threshold,timerange=timerange)#,markall=markall)
            self.flaglist.extend(flaglist)
            self.plotstream = self.plotstream.flag_outlier(stdout=True, keys=keys,threshold=threshold,timerange=timerange)
            self.menu_p.rep_page.logMsg('- flagged outliers: added {} flags'.format(len(flaglist)))
        except:
            print("flag outliers failed: check parameter")
            self.menu_p.rep_page.logMsg('- flag outliers failed: check parameter')

        self.ActivateControls(self.plotstream)
        self.annotate = True
        self.menu_p.str_page.annotateCheckBox.SetValue(True)
        self.OnPlot(self.plotstream,self.shownkeylist,padding=self.padding, specialdict=self.specialdict,errorbars=self.errorbars,colorlist=self.colorlist, symbollist=self.symbollist,annotate=self.annotate,stormphases=self.stormphases, t_stormphases=self.t_stormphases,includeid=self.includeid,function=self.function, plottype=self.plottype,labels=self.labels,resolution=self.resolution,confinex=self.confinex)
        self.changeStatusbar("Ready")


    def onFlagRangeButton(self,event):
        """
        DESCRIPTION
            Opens a dialog which allows to select the range to be flagged
        """
        sensid = self.plotstream.header.get('SensorID','')
        dataid = self.plotstream.header.get('DataID','')
        if sensid == '' and not dataid == '':
            sensid = dataid[:-5]

        if sensid == '':
            dlg = wx.MessageDialog(self, "No Sensor ID available!\n"
                            "You need to define a unique Sensor ID\nfor the data set in order to use flagging.\nPlease go the tab Meta for this purpose.\n","Undefined Sensor ID", wx.OK|wx.ICON_INFORMATION)
            dlg.ShowModal()
            dlg.Destroy()
        else:
            self.changeStatusbar("Flagging range ...")
            dlg = StreamFlagRangeDialog(None, title='Stream: Flag range', stream = self.plotstream, shownkeylist=self.shownkeylist, keylist=self.keylist)
            dlg.startFlagDatePicker.SetValue(pydate2wxdate(num2date(self.plotstream.ndarray[0][0])))
            dlg.endFlagDatePicker.SetValue(pydate2wxdate(num2date(self.plotstream.ndarray[0][-1])))
            if dlg.ShowModal() == wx.ID_OK:
                # get values from dlg
                flagtype = dlg.rangeRadioBox.GetStringSelection()
                keys2flag = dlg.AffectedKeysTextCtrl.GetValue()
                keys2flag = keys2flag.split(',')
                keys2flag = [el for el in keys2flag if el in KEYLIST]
                comment = dlg.CommentTextCtrl.GetValue()
                flagid = dlg.FlagIDComboBox.GetValue()
                flagid = int(flagid[0])
                if flagtype == 'value':
                     keys = str(dlg.SelectKeyComboBox.GetValue())
                     above = dlg.LowerLimitTextCtrl.GetValue()
                     below = dlg.UpperLimitTextCtrl.GetValue()
                     flagval = True
                     if not below == '' and not above == '':
                         above = float(above)
                         below = None
                         self.menu_p.rep_page.logMsg('- flagging values above {} - ignoring upper limit'.format(above))
                     elif not below == '':
                         below = float(below)
                         above = None
                         self.menu_p.rep_page.logMsg('- flagging values below {}'.format(below))
                     elif not above == '':
                         above = float(above)
                         below = None
                         self.menu_p.rep_page.logMsg('- flagging values above {}'.format(above))
                     else:
                         flagval = False
                     if flagval:
                         print ("Above , Below:", above, below) 
                         flaglist = self.plotstream.flag_range(keys=[keys],flagnum=flagid,text=comment,keystoflag=keys2flag,above=above,below=below)
                         self.menu_p.rep_page.logMsg('- flagged value range: added {} flags'.format(len(flaglist)))
                elif flagtype == 'time':
                     if comment == '':
                         comment = 'Time range flagged with unspecified reason'
                     stday = dlg.startFlagDatePicker.GetValue()
                     sttime = str(dlg.startFlagTimePicker.GetValue())
                     sd = datetime.strftime(datetime.fromtimestamp(stday.GetTicks()), "%Y-%m-%d")
                     starttime= datetime.strptime(str(sd)+'_'+sttime, "%Y-%m-%d_%H:%M:%S")
                     enday = dlg.endFlagDatePicker.GetValue()
                     entime = str(dlg.endFlagTimePicker.GetValue())
                     ed = datetime.strftime(datetime.fromtimestamp(enday.GetTicks()), "%Y-%m-%d")
                     endtime= datetime.strptime(str(ed)+'_'+entime, "%Y-%m-%d_%H:%M:%S")
                     flaglist = self.plotstream.flag_range(keys=self.shownkeylist,flagnum=flagid,text=comment,keystoflag=keys2flag,starttime=starttime,endtime=endtime)
                     self.menu_p.rep_page.logMsg('- flagged time range: added {} flags'.format(len(flaglist)))
                else:
                     pass

        if len(flaglist) > 0:
            print ("FlagRange: Please note that the range definition needs an update as only single values are considered")
            self.flaglist.extend(flaglist)
            self.plotstream = self.plotstream.flag(flaglist)

            self.ActivateControls(self.plotstream)
            self.annotate = True
            self.menu_p.str_page.annotateCheckBox.SetValue(True)
            self.OnPlot(self.plotstream,self.shownkeylist,padding=self.padding, specialdict=self.specialdict,errorbars=self.errorbars,colorlist=self.colorlist, symbollist=self.symbollist,annotate=self.annotate,stormphases=self.stormphases, t_stormphases=self.t_stormphases,includeid=self.includeid,function=self.function, plottype=self.plottype,labels=self.labels,resolution=self.resolution,confinex=self.confinex)

        self.changeStatusbar("Ready")


    def onFlagLoadButton(self,event):
        """
        DESCRIPTION
            Opens a dialog which allows to load flags either from a DB or from file
        """
        sensorid = self.plotstream.header.get('SensorID','')
        # Open Dialog and return the parameters threshold, keys, timerange
        self.changeStatusbar("Loading flags ... please be patient")
        dlg = StreamLoadFlagDialog(None, title='Load Flags', db = self.db, sensorid=sensorid)
        dlg.ShowModal()
        if len(dlg.flaglist) > 0:
            flaglist = dlg.flaglist
            #print ("Loaded flags", len(flaglist))
            self.flaglist.extend(flaglist)
            self.changeStatusbar("Applying flags ... please be patient")
            self.plotstream = self.plotstream.flag(flaglist)
            self.menu_p.rep_page.logMsg('- loaded flags: added {} flags'.format(len(flaglist)))

            self.ActivateControls(self.plotstream)
            self.annotate = True
            self.menu_p.str_page.annotateCheckBox.SetValue(False)
            self.OnPlot(self.plotstream,self.shownkeylist,padding=self.padding, specialdict=self.specialdict,errorbars=self.errorbars,colorlist=self.colorlist, symbollist=self.symbollist,annotate=self.annotate,stormphases=self.stormphases, t_stormphases=self.t_stormphases,includeid=self.includeid,function=self.function, plottype=self.plottype,labels=self.labels,resolution=self.resolution,confinex=self.confinex)

        self.changeStatusbar("Ready")


    def onFlagSaveButton(self,event):
        """
        DESCRIPTION
            Opens a dialog which allows to save flags either to DB or to file
        """
        currentlen = len(self.flaglist)

        self.changeStatusbar("Saving flags ...")
        dlg = StreamSaveFlagDialog(None, title='Save Flags', db = self.db, flaglist=self.flaglist)
        if dlg.ShowModal() == wx.ID_OK:
            #flaglist = dlg.flaglist
            pass

        self.changeStatusbar("Ready")


    def onFlagDropButton(self,event):
        """
        DESCRIPTION
            Drops all flagged data
        """
        self.changeStatusbar("Dropping flagged data ...")

        #dlg = wx.MessageDialog(self, "Please select:\n"
        #       "Yes: drop data from all columns\nNo: drop only selected data\n","Drop", wx.YES_NO |wx.ICON_INFORMATION)
        #if dlg.ShowModal() == wx.ID_YES:
        #    self.plotstream = self.plotstream.flag(self.shownkeylist)
        #else:
        self.plotstream = self.plotstream.remove_flagged()
        #flagidx = KEYLIST.index('flag')
        #commidx = KEYLIST.index('comment')
        self.plotstream = self.plotstream._drop_column('flag')
        self.plotstream = self.plotstream._drop_column('comment')

        self.menu_p.rep_page.logMsg('- flagged data removed')

        self.flaglist = []
        self.ActivateControls(self.plotstream)
        self.annotate = False
        self.menu_p.str_page.annotateCheckBox.SetValue(False)
        self.OnPlot(self.plotstream,self.shownkeylist,padding=self.padding, specialdict=self.specialdict,errorbars=self.errorbars,colorlist=self.colorlist, symbollist=self.symbollist,annotate=self.annotate,stormphases=self.stormphases, t_stormphases=self.t_stormphases,includeid=self.includeid,function=self.function, plottype=self.plottype,labels=self.labels,resolution=self.resolution,confinex=self.confinex)

        self.changeStatusbar("Ready")



    # ------------------------------------------------------------------------------------------
    # ################
    # Meta page functions
    # ################
    # ------------------------------------------------------------------------------------------


    def onMetaGetDBButton(self,event):
        # TODO Move to Meta page
        """
        DESCRIPTION
            get Meta data for the current sensorid from database
        """
        # open dialog with all header info
        dataid = self.plotstream.header.get('DataID','')
        if dataid == '':
            dlg = wx.MessageDialog(self, "No Data ID available!\n"
                            "You need to specify a unique Data ID\nfor which meta information is obtained.\n","Undefined Data ID", wx.OK|wx.ICON_INFORMATION)
            dlg.ShowModal()
            dlg.Destroy()
            self.menu_p.rep_page.logMsg(" - failed to add meta information from DB")
        else:
            self.plotstream.header = dbfields2dict(self.db,dataid)
            self.menu_p.rep_page.logMsg(" - added meta information for {} from DB".format(dataid))
            self.ActivateControls(self.plotstream)


    def onMetaPutDBButton(self,event):
        """
        DESCRIPTION
            write meta data to the database
        """
        # open dialog with all header info
        dataid = self.plotstream.header.get('DataID','')
        if dataid == '':
            dlg = wx.MessageDialog(self, "No Data ID available!\n"
                            "You need to specify a unique Data ID\nfor which meta information is stored.\n","Undefined Data ID", wx.OK|wx.ICON_INFORMATION)
            dlg.ShowModal()
            dlg.Destroy()
            self.menu_p.rep_page.logMsg(" - failed to add meta information to DB")
        else:
            dlg = wx.MessageDialog(self, "Please confirm!\n"
                            "I want to replace the Meta information\nfrom the DB with data provided.\n","Confirm", wx.YES_NO |wx.ICON_INFORMATION)
            if dlg.ShowModal() == wx.ID_YES:
                dbdict2fields(self.db,self.plotstream.header)
                self.menu_p.rep_page.logMsg(" - added meta information for {} to DB".format(dataid))
            dlg.Destroy()
            self.ActivateControls(self.plotstream)

    def onMetaDataButton(self,event):
        """
        DESCRIPTION
            open dialog to modify plot options (general (e.g. bgcolor) and  key
            specific (key: symbol color errorbar etc)
        """
        # open dialog with all header info
        if len(self.plotstream.ndarray[0]) > 0:
            dlg = MetaDataDialog(None, title='Meta information:',header=self.plotstream.header,layer='DATAINFO')
            if dlg.ShowModal() == wx.ID_OK:
                for key in DATAINFOKEYLIST:
                    exec('value = dlg.'+key+'TextCtrl.GetValue()')
                    if not value == dlg.header.get(key,''):
                        self.plotstream.header[key] = value
                self.ActivateControls(self.plotstream)
        else:
            self.menu_p.rep_page.logMsg("Meta information: No data available")


    def onMetaSensorButton(self,event):
        # TODO Move to Meta page
        """
        DESCRIPTION
        open dialog to modify plot options (general (e.g. bgcolor) and  key
        specific (key: symbol color errorbar etc)
        """
        # open dialog with all header info
        if len(self.plotstream.ndarray[0]) > 0:
            dlg = MetaDataDialog(None, title='Meta information:',header=self.plotstream.header,layer='SENSORS')
            if dlg.ShowModal() == wx.ID_OK:
                for key in SENSORSKEYLIST:
                    exec('value = dlg.'+key+'TextCtrl.GetValue()')
                    if not value == dlg.header.get(key,''):
                        self.plotstream.header[key] = value
                self.ActivateControls(self.plotstream)

        else:
            self.menu_p.rep_page.logMsg("Meta information: No data available")


    def onMetaStationButton(self,event):
        # TODO Move to Meta page
        """
        DESCRIPTION
        open dialog to modify plot options (general (e.g. bgcolor) and  key
        specific (key: symbol color errorbar etc)
        """
        # open dialog with all header info
        if len(self.plotstream.ndarray[0]) > 0:
            dlg = MetaDataDialog(None, title='Meta information:',header=self.plotstream.header,layer='STATIONS')
            if dlg.ShowModal() == wx.ID_OK:
                for key in STATIONSKEYLIST:
                    exec('value = dlg.'+key+'TextCtrl.GetValue()')
                    if not value == dlg.header.get(key,''):
                        self.plotstream.header[key] = value
                self.ActivateControls(self.plotstream)
        else:
            self.menu_p.rep_page.logMsg("Meta information: No data available")

    # ------------------------------------------------------------------------------------------
    # ####################
    # Stream Operations functions
    # ####################
    # ------------------------------------------------------------------------------------------

    def OnStreamList(self,event):
        """
        DESCRIPTION
        open dialog to select active stream
        """
        pass



    # ------------------------------------------------------------------------------------------
    # ################
    # Absolute functions
    # ################
    # ------------------------------------------------------------------------------------------


    def onLoadDI(self,event):
        """
        open dialog to load DI data
        """
        if len(self.stream) > 0:
            pass
            # send a message box that this data will be erased

        dlg = LoadDIDialog(None, title='Get DI data', dirname=self.dipathlist)
        dlg.ShowModal()
        if not dlg.pathlist == 'None' and not len(dlg.pathlist) == 0:
            self.menu_p.rep_page.logMsg("- loaded DI data")
            self.menu_p.abs_page.diTextCtrl.SetValue(', '.join(dlg.pathlist))
            self.dipathlist = dlg.pathlist
            self.menu_p.abs_page.AnalyzeButton.Enable()

        dlg.Destroy()


    def onDefineVario(self,event):
        """
        open dialog to load DI data
        """
        if len(self.stream) > 0:
            pass
            # send a message box that this data will be erased

        #self.variopath = ''
        # Open a select path dlg as long as db and remote is not supported
        dialog = wx.DirDialog(None, "Choose a directory with variometer data:",self.divariopath,style=wx.DD_DEFAULT_STYLE | wx.DD_NEW_DIR_BUTTON)
        if dialog.ShowModal() == wx.ID_OK:
            path = dialog.GetPath()
            self.menu_p.abs_page.varioTextCtrl.SetValue(path)
            self.divariopath = os.path.join(path,'*')
        dialog.Destroy()
        """
        dlg = DefineVarioDialog(None, title='Get Variometer path')
        if dlg.ShowModal() == wx.ID_OK:
            self.menu_p.abs_page.varioTextCtrl.SetValue(dlg.path)
            self.divariopath = os.path.join(dlg.path,'*')
        dlg.Destroy()
        """

    def onDefineScalar(self,event):
        """
        open dialog to load DI data
        """
        if len(self.stream) > 0:
            pass
            # send a message box that this data will be erased
        # Open a select path dlg as long as db and remote is not supported
        dialog = wx.DirDialog(None, "Choose a directory with scalar data:",self.discalarpath,style=wx.DD_DEFAULT_STYLE | wx.DD_NEW_DIR_BUTTON)
        if dialog.ShowModal() == wx.ID_OK:
            path = dialog.GetPath()
            self.menu_p.abs_page.varioTextCtrl.SetValue(path)
            self.discalarpath = os.path.join(path,'*')
        dialog.Destroy()
        """
        dlg = DefineScalarDialog(None, title='Get path for scalar data')
        if dlg.ShowModal() == wx.ID_OK:
            self.menu_p.abs_page.scalarTextCtrl.SetValue(dlg.path)
            self.discalarpath = os.path.join(dlg.path,'*')
        dlg.Destroy()
        """

    def onDIAnalyze(self,event):
        """
        open dialog to load DI data
        """
        if len(self.dipathlist) > 0:
            self.changeStatusbar("Processing DI data ...")
            #absstream = absoluteAnalysis(self.dipathlist,self.divariopath,self.discalarpath, expD=self.diexpD,expI=self.diexpI,diid=self.diid,stationid=self.stationid,abstype=self.ditype, azimuth=self.diazimuth,pier=self.dipier,alpha=self.dialpha,deltaF=self.dideltaF, dbadd=self.didbadd)
            prev_redir = sys.stdout
            redir=RedirectText(self.menu_p.abs_page.dilogTextCtrl)
            sys.stdout=redir
            print("Paths:", self.divariopath,self.discalarpath)
            if not self.diazimuth == '':
                absstream = absoluteAnalysis(self.dipathlist,self.divariopath,self.discalarpath, expD=self.diexpD,expI=self.diexpI,stationid=self.stationid,abstype=self.ditype, azimuth=self.diazimuth,alpha=self.dialpha,deltaF=self.dideltaF)
            else:
                absstream = absoluteAnalysis(self.dipathlist,self.divariopath,self.discalarpath, expD=self.diexpD,expI=self.diexpI,stationid=self.stationid)

            sys.stdout=prev_redir
            # only if more than one point is selected
            self.changeStatusbar("Ready")
            if absstream.length()[0] > 1:
                self.stream = absstream
                self.plotstream = absstream
                currentstreamindex = len(self.streamlist)
                self.streamlist.append(self.stream)
                self.headerlist.append(self.stream.header)
                self.currentstreamindex = currentstreamindex
                self.ActivateControls(self.plotstream)
                self.OnInitialPlot(self.plotstream)

            #redir=RedirectText(self.menu_p.rep_page.logMsg)
            #sys.stdout=prev_redir


    def onDISetParameter(self,event):
        """
        open parameter box for DI analysis
        """

        dlg = DISetParameterDialog(None, title='Set Parameter')
        dlg.expDTextCtrl.SetValue(str(self.diexpD))
        dlg.deltaFTextCtrl.SetValue(str(self.dideltaF))
        dlg.azimuthTextCtrl.SetValue(str(self.diazimuth))
        dlg.alphaTextCtrl.SetValue(str(self.dialpha))

        if dlg.ShowModal() == wx.ID_OK:
            if not dlg.expDTextCtrl.GetValue() == '':
                self.diexpD = float(dlg.expDTextCtrl.GetValue())
            if not dlg.azimuthTextCtrl.GetValue() == '':
                self.diazimuth = float(dlg.azimuthTextCtrl.GetValue())
            if not dlg.pierTextCtrl.GetValue() == '':
                self.dipier = dlg.pierTextCtrl.GetValue()
            if not dlg.alphaTextCtrl.GetValue() == '':
                self.dialpha = float(dlg.alphaTextCtrl.GetValue())
            if not dlg.deltaFTextCtrl.GetValue() == '':
                self.dideltaF = float(dlg.deltaFTextCtrl.GetValue())

        dlg.Destroy()


    def onInputSheet(self,event):
        """
        DESCRITPTION:
            open dialog to input DI data
        """

        if isinstance(self.dipathlist, str):
            dipath = self.dipathlist            
        else:
            dipath = self.dipathlist[0]
        self.dilayout = {'order':['MU','MD','EU','WU','ED','WD','NU','SD','ND','SU'], 'scalevalue':'True', 'double':'True'}
        cdate = pydate2wxdate(datetime.utcnow())
        defaults = {'pier':'A2'}
        dlg = InputSheetDialog(None, title='Add DI data',path=dipath,layout=self.dilayout, defaults=defaults, cdate=cdate)
        if dlg.ShowModal() == wx.ID_OK:
            pass
        dlg.Destroy()


    def onSaveDIData(self, event):
        """
        DESCRIPTION
            Save data of the logger to file
        """
        # TODO When starting ANalysis -> stout is redirected .. switch back to normal afterwards
        saveFileDialog = wx.FileDialog(self, "Save As", "", "", 
                                       "DI analysis report (*.txt)|*.txt", 
                                       wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        saveFileDialog.ShowModal()
        savepath = saveFileDialog.GetPath()
        text = self.menu_p.abs_page.dilogTextCtrl.GetValue()
        saveFileDialog.Destroy()

        difile = open(savepath, "w")
        difile.write(text)
        difile.close()


    def onClearDIData(self, event):
        self.menu_p.abs_page.dilogTextCtrl.SetValue('')

    # ------------------------------------------------------------------------------------------
    # ################
    # Report page functions
    # ################
    # ------------------------------------------------------------------------------------------


    def onSaveLogButton(self, event):
        saveFileDialog = wx.FileDialog(self, "Save As", "", "", 
                                       "Log files (*.log)|*.log", 
                                       wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        saveFileDialog.ShowModal()
        saveFileDialog.GetPath()
        saveFileDialog.Destroy()


    # ------------------------------------------------------------------------------------------
    # ################
    # Monitor page functions
    # ################
    # ------------------------------------------------------------------------------------------

    def onConnectMARTASButton(self, event):
        # start a subscribe to client call
        # continuously collect data to stream and periodically call monitor plots 
        success = False
        if success:
            self.menu_p.com_page.startMonitorButton.Enable()
            self.menu_p.com_page.coverageTextCtrl.Enable()    # always
            self.menu_p.com_page.frequSlider.Enable()         # always


    def onConnectMARCOSButton(self, event):
        # active if database is connected
        # open dlg
        self.menu_p.rep_page.logMsg('- Selecting MARCOS table for monitoring ...')
        output = dbselect(self.db,'DataID,DataMinTime,DataMaxTime','DATAINFO')
        datainfoidlist = [elem[0] for elem in output]
        if len(datainfoidlist) < 1:
            dlg = wx.MessageDialog(self, "No data tables available!\n"
                            "please check your database\n",
                            "OpenDB", wx.OK|wx.ICON_INFORMATION)
            dlg.ShowModal()
            dlg.Destroy()
            return
        # select table
        sr = 1
        dlg = AGetMARCOSDialog(None, title='Select table',datalst=datainfoidlist)
        if dlg.ShowModal() == wx.ID_OK:
            datainfoid = dlg.dataComboBox.GetValue()
            vals = dbselect(self.db, 'SensorID,DataSamplingRate,ColumnContents,ColumnUnits','DATAINFO', 'DataID = "'+datainfoid+'"')
            vals = vals[0]
            sensid= vals[0]
            sr= float(vals[1].strip('sec'))
            keys= vals[2].split(',')
            units= vals[3].split(',')
        else:
            dlg.Destroy()
            return
        # get all parameters

        pad = 5
        currentdate = datetime.strftime(datetime.utcnow(),"%Y-%m-%d")

        # start monitoring parameters
        period = float(self.menu_p.com_page.frequSlider.GetValue())
        covval = float(self.menu_p.com_page.coverageTextCtrl.GetValue())
        coverage = covval/sr
        limit = period/sr
        unitlist = []
        for idx,key in enumerate(keys):
           if not key == '':
               unitlist.append([key, units[idx]])

        parameter = ','.join([key for key in keys if not key=='' and key in NUMKEYLIST])

        self.plot_p.datavars = {0: datainfoid, 1: parameter, 2: limit, 3: pad, 4: currentdate, 5: unitlist, 6: coverage, 7: period, 8: self.db}
        self.monitorSource='MARCOS'

        success = True
        if success:
            self.menu_p.com_page.startMonitorButton.Enable()
            self.menu_p.com_page.getMARTASButton.Disable()
            self.menu_p.com_page.getMQTTButton.Disable()
            self.menu_p.com_page.marcosLabel.SetBackgroundColour(wx.GREEN)
            self.menu_p.com_page.marcosLabel.SetValue('connected to {}'.format(self.dbname))
            self.menu_p.com_page.logMsg('Begin monitoring...')
            self.menu_p.com_page.logMsg(' - Selected MARCOS database')
            self.menu_p.com_page.logMsg(' - Table: {}'.format(datainfoid))
            self.menu_p.com_page.coverageTextCtrl.Enable()    # always
            self.menu_p.com_page.frequSlider.Enable()         # always


    def onConnectMQTTButton(self, event):
        success = False
        if success:
            self.menu_p.com_page.startMonitorButton.Enable()
            self.menu_p.com_page.coverageTextCtrl.Enable()    # always
            self.menu_p.com_page.frequSlider.Enable()         # always


    def onStartMonitorButton(self, event):
        self.DeactivateAllControls()
        self.menu_p.com_page.getMARTASButton.Disable()
        self.menu_p.com_page.getMARCOSButton.Disable()
        self.menu_p.com_page.getMQTTButton.Disable()
        self.menu_p.com_page.stopMonitorButton.Enable()
        self.menu_p.com_page.saveMonitorButton.Enable()

        # start monitoring parameters
        period = float(self.menu_p.com_page.frequSlider.GetValue())
        covval = float(self.menu_p.com_page.coverageTextCtrl.GetValue())
        sr = self.plot_p.datavars[7]/self.plot_p.datavars[2]
        coverage = covval/sr
        limit = period/sr
        self.plot_p.datavars[2] = limit
        self.plot_p.datavars[6] = coverage
        self.plot_p.datavars[7] = period

        # Obtain the last values from the data base with given dataid and limit
        # A DB query for 10 min 10Hz data needs approx 0.3 sec
        if  self.monitorSource=='MARCOS':
            self.plot_p.t1_stop.clear()
            self.menu_p.com_page.logMsg(' > Starting read cycle... {} sec'.format(period))
            self.plot_p.startMARCOSMonitor()
            self.menu_p.com_page.marcosLabel.SetBackgroundColour(wx.GREEN)
            self.menu_p.com_page.marcosLabel.SetValue('connected to {}'.format(self.dbname))


    def onStopMonitorButton(self, event):
        if  self.monitorSource=='MARCOS':
            self.plot_p.t1_stop.set()
            self.menu_p.com_page.logMsg(' > Read cycle stopped')
            self.menu_p.com_page.logMsg('MARCOS disconnected')

            # convert array to stream   self.plot_p.array
        self.menu_p.com_page.stopMonitorButton.Disable()
        self.menu_p.com_page.saveMonitorButton.Disable()
        self.ActivateControls(DataStream())
        self.menu_p.com_page.getMARTASButton.Enable()
        self.menu_p.com_page.getMARCOSButton.Enable()
        self.menu_p.com_page.getMQTTButton.Enable()
        self.menu_p.com_page.marcosLabel.SetBackgroundColour((255,23,23))
        self.menu_p.com_page.martasLabel.SetBackgroundColour((255,23,23))
        self.menu_p.com_page.mqttLabel.SetBackgroundColour((255,23,23))
        self.menu_p.com_page.marcosLabel.SetValue('not connected')
        self.menu_p.com_page.martasLabel.SetValue('not connected')
        self.menu_p.com_page.mqttLabel.SetValue('not connected')


    def onLogDataButton(self, event):
        # open dialog with pathname
        # then use data_2_file method for binary writing
        pass

'''
# To run:
app = wx.App(redirect=False)
frame = MainFrame(None,-1,"")
frame.Show()
app.MainLoop()
'''

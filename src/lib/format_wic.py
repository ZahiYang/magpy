"""
MagPy
Auxiliary input filter - WIC/WIK
Supports USB temperature loggers, RCS files, old Caesium data and SG data
Written by Roman Leonhardt June 2012
- contains test and read function, toDo: write function
"""

from stream import *

def isUSBLOG(filename):
    """
    Checks whether a file is ASCII USB-Logger format.
    Supports temperture and humidity logger
    Extend that code for CO logger as well
    """
    try:
        temp = open(filename, 'rt').readline()
    except:
        return False
    sp = temp.split(',')
    if not len(sp) == 6:
        return False
    if not sp[1] == 'Time':
        return False
    return True


def isRMRCS(filename):
    """
    Checks whether a file is ASCII RCS format.
    """
    try:
        temp = open(filename, 'rt').readline()
    except:
        return False
    if not temp.startswith('# RCS'):
        return False
    return True


def isGRAVSG(filename):
    """
    Checks whether a file is ASCII SG file format.
    """

    try:
        temp = open(filename, 'rt').readline()
    except:
        return False
    if not temp.startswith('[TSF-file]'):
        return False
    return True


def isCS(filename):
    """
    Checks whether a file is ASCII CS Mag and initial ws format.
    should be called as one of the last options
    """
    try:
        temp = open(filename, 'rt').readline()
    except:
        return False
    tmp = temp.split()
    if not len(tmp) in [2,4]:
        return False
    try:
        testdate = datetime.strptime(tmp[0].strip(','),"%H:%M:%S.%f")
    except:
        try:
            testdate = datetime.strptime(tmp[0],"%Y-%m-%dT%H:%M:%S.%f")
        except:
            return False
    return True

def readRMRCS(filename, headonly=False, **kwargs):
    """
    Reading RMRCS format data. (Richard Mandl's RCS extraction)
    # RCS Fieldpoint T7
    # Conrad Observatorium, www.zamg.ac.at
    # 2012-02-01 00:00:00
    # 
    # 12="ZAGTFPT7	M6	I,cFP-AI-110	CH00	AP23	Niederschlagsmesser	--	Unwetter, S	AR0-20H0.1	mm	y=500x+0	AI"
    # 13="ZAGTFPT7	M6	I,cFP-AI-110	CH01	JC	Schneepegelsensor	OK	Mastverwehung, S	AR0-200H0	cm	y=31250x+0	AI"
    # 14="ZAGTFPT7	M6	I,cFP-AI-110	CH02	430A_T	Wetterhuette - Lufttemperatur	-	-, B	AR-35-45H0	C	y=4000x-35	AI"
    # 15="ZAGTFPT7	M6	I,cFP-AI-110	CH03	430A_F	Wetterhuette - Luftfeuchte	-	-, B	AR0-100H0	%	y=5000x+0	AI"
    # 
    1328054403.99	20120201 000004	49.276E-6	49.826E+0	-11.665E+0	78.356E+0
    1328054407.99	20120201 000008	79.480E-6	49.823E+0	-11.677E+0	78.364E+0
    1328054411.99	20120201 000012	68.555E-6	49.828E+0	-11.688E+0	78.389E+0
    """
    starttime = kwargs.get('starttime')
    endtime = kwargs.get('endtime')
    getfile = True

    fh = open(filename, 'rt')
    # read file and split text into channels
    # --------------------------------------
    stream = DataStream()
    # Check whether header infromation is already present
    if stream.header is None:
        headers = {}
    else:
        headers = stream.header
    data = []
    measurement = []
    unit = []
    i = 0
    key = None

    # try to get day from filename (platform independent)
    # --------------------------------------
    splitpath = os.path.split(filename)
    tmpdaystring = splitpath[1].split('.')[0].split('_')
    tmpdaystring = tmpdaystring[0].replace('-','')
    daystring = re.findall(r'\d+',tmpdaystring)[0]
    if len(daystring) >  8:
        daystring = daystring[-8:]
    try:
        day = datetime.strftime(datetime.strptime(daystring, "%Y%m%d"),"%Y-%m-%d")
        # Select only files within eventually defined time range
        if starttime:
            if not datetime.strptime(day,'%Y-%m-%d') >= datetime.strptime(datetime.strftime(stream._testtime(starttime),'%Y-%m-%d'),'%Y-%m-%d'):
                getfile = False
        if endtime:
            if not datetime.strptime(day,'%Y-%m-%d') <= datetime.strptime(datetime.strftime(stream._testtime(endtime),'%Y-%m-%d'),'%Y-%m-%d'):
                getfile = False
    except:
        logging.warning("Could not identify date in filename %s - reading all" % filename)
        getfile = True
        pass

    if getfile:
        for line in fh:
            if line.isspace():
                # blank line
                pass
            elif line.startswith('#'):
                # data header
                colsstr = line.split(',')
                if (len(colsstr) == 3):
                    # select the lines with three komma separaeted parts -> they describe the data
                    meastype = colsstr[1].split()
                    unittype = colsstr[2].split()
                    measurement.append(meastype[2])
                    unit.append(unittype[2])
                    headers['col-'+KEYLIST[i+1]] = unicode(measurement[i],errors='ignore')
                    headers['unit-col-'+KEYLIST[i+1]] = unicode(unit[i],errors='ignore')
                    i=i+1
            elif headonly:
                # skip data for option headonly
                continue
            else:
                # data entry - may be written in multiple columns
                # row beinhaltet die Werte eine Zeile
                elem = string.split(line[:-1])
                row = LineStruct()
                try:
                    row.time = date2num(datetime.strptime(elem[1],"%Y-%m-%dT%H:%M:%S"))
                    add = 2
                except:
                    try:
                        row.time = date2num(datetime.strptime(elem[1]+'T'+elem[2],"%Y%m%dT%H%M%S"))
                        add = 3
                    except:
                        raise ValueError, "Can't read date format in RCS file"
                for i in range(len(unit)):
                    try:
                        #print eval('elem['+str(i+add)+']')
                        exec('row.'+KEYLIST[i+1]+' = float(elem['+str(i+add)+'])')
                    except:
                        pass
                stream.add(row)         
    else:
        headers = stream.header
        stream =[]

    fh.close()

    return DataStream(stream, headers)    



def readUSBLOG(filename, headonly=False, **kwargs):
    """
    Reading ASCII USB DataLogger Structure format data.

    Vario,Time,Celsius(deg C),Humidity(%rh),dew point(deg C),Serial Number
    3,29/07/2010 12:58:03,21.0,88.5,19.0
    4,29/07/2010 13:28:03,21.0,88.5,19.0
    5,29/07/2010 13:58:03,21.0,88.5,19.0
    6,29/07/2010 14:28:03,21.0,88.5,19.0
    7,29/07/2010 14:58:03,21.0,89.0,19.1
    8,29/07/2010 15:28:03,21.0,89.0,19.1
    """
    stream = DataStream()
    # Check whether header infromation is already present
    if stream.header == None:
        headers = {}
    else:
        headers = stream.header
    qFile= file( filename, "rb" )
    csvReader= csv.reader( qFile )
    for elem in csvReader:
        row = LineStruct()
        try:
            if elem[1] == 'Time':
                el2 = elem[2].split('(')
                test = el2[1]
                headers['unit-col-t1'] = "\circ C" #unicode(el2[1].strip(')'),errors='ignore')
                headers['col-t1'] = 'T'
                el3 = elem[3].split('(')
                headers['unit-col-var1'] = "percent" #unicode(el3[1].strip(')'),errors='ignore')
                headers['col-var1'] = 'RH'
                el4 = elem[4].split('(')
                headers['unit-col-t2'] = "\circ C" #unicode(el4[1].strip(')'),errors='ignore')
                headers['col-t2'] = 'T(dew)'
            elif len(elem) == 6 and not elem[1] == 'Time':
                headers['SensorSerialNum'] = '%s' % elem[5]
            else:
                row.time = date2num(datetime.strptime(elem[1],"%d/%m/%Y %H:%M:%S"))
                row.t1 = float(elem[2])
                row.var1 = float(elem[3])
                row.t2 = float(elem[4])
                stream.add(row)
        except:
            pass
    qFile.close()
    # Add some Sensor specific header information
    headers['SensorDescription'] = 'Model HMHT-LG01: This Humidity and Temperature USB data logger measures and stores relative humidity temperature readings over 0 to 100 per RH and -35 to +80 deg C measurement ranges. Humidity: Repeatability (short term) 0.1 per RH, Accuracy (overall error) 3.0* 6.0 per RH, Internal resolution 0.5 per RH, Long term stability 0.5 per RH/Yr; Temperature: Repeatability 0.1 deg C, Accuracy (overall error) 0.5 and 2  deg C, Internal resolution 0.5 deg C'
    headers['SensorName'] = 'HMHT-LG01'
    headers['SensorType'] = 'Temperature/Humidity'

    return DataStream(stream, headers)    


def readCS(filename, headonly=False, **kwargs):
    """
    Reading ASCII PyMagStructure format data.
    """
    starttime = kwargs.get('starttime')
    endtime = kwargs.get('endtime')

    stream = DataStream()
    # Check whether header infromation is already present
    if stream.header == None:
        headers = {}
    else:
        headers = stream.header
    qFile= file( filename, "rb" )
    csvReader= csv.reader( qFile )

    # get day from filename (platform independent)
    getfile = True
    theday = extractDateFromString(filename)
    day = datetime.strftime(theday,'%Y-%m-%d')
    try:
        if starttime:
            if not datetime.strptime(day,'%Y-%m-%d') >= datetime.strptime(datetime.strftime(stream._testtime(starttime),'%Y-%m-%d'),'%Y-%m-%d'):
                getfile = False
        if endtime:
            if not datetime.strptime(day,'%Y-%m-%d') <= datetime.strptime(datetime.strftime(stream._testtime(endtime),'%Y-%m-%d'),'%Y-%m-%d'):
                getfile = False
    except:
        try:
            theday = extractDateFromString(filename)
            day = datetime.strftime(theday,"%Y-%m-%d")
            if starttime:
                if not datetime.strptime(day,'%Y-%m-%d') >= stream._testtime(starttime):
                    getfile = False
            if endtime:
                if not datetime.strptime(day,'%Y-%m-%d') <= stream._testtime(endtime):
                    getfile = False
        except:
            logging.warning("Wrong dateformat in Filename %s" % daystring)
            getfile = True

    # Select only files within eventually defined time range
    if getfile:
        logging.info(' Read: %s Format: CS (txt) ' % (filename))
        for elem in csvReader:
            if len(elem) == 1:
                elem = elem[0].split()
            if elem[0]=='#':
                # blank line
                pass
            elif headonly:
                # skip data for option headonly
                continue
            else:
                try:
                    row = LineStruct()
                    try:
                        row.time = date2num(datetime.strptime(day+'T'+elem[0],"%Y-%m-%dT%H:%M:%S.%f"))
                    except:
                        row.time = date2num(datetime.strptime(elem[0],"%Y-%m-%dT%H:%M:%S.%f"))
                    if len(elem) == 2:
                        row.f = float(elem[1])
                    elif len(elem) == 4:
                        row.t1 = float(elem[1])
                        row.var1 = float(elem[2])
                        row.t2 = float(elem[3])

                    stream.add(row)
                except ValueError:
                    pass
        qFile.close()

        if len(elem) == 2:
            headers['unit-col-f'] = 'nT' 
            headers['col-f'] = 'F' 
        elif len(elem) == 4:
            headers['unit-col-t1'] = 'deg C' 
            headers['unit-col-t2'] = 'deg C' 
            headers['unit-col-var1'] = 'percent' 
            headers['col-t1'] = 'T' 
            headers['col-t2'] = 'Dewpoint' 
            headers['col-var1'] = 'RH' 

    return DataStream(stream, headers)    


def readGRAVSG(filename, headonly=False, **kwargs):
    """
    Reading SG-Gravity data files.
    """

    starttime = kwargs.get('starttime')
    endtime = kwargs.get('endtime')
    getfile = True

    stream = DataStream()
    
    # Check whether header infromation is already present
    if stream.header == None:
        headers = {}
    else:
        headers = stream.header

    theday = extractDateFromString(filename)

    try:
        if starttime:
            if not theday >= datetime.strptime(datetime.strftime(stream._testtime(starttime),'%Y-%m-%d'),'%Y-%m-%d'):
                getfile = False
        if endtime:
            if not theday <= datetime.strptime(datetime.strftime(stream._testtime(endtime),'%Y-%m-%d'),'%Y-%m-%d'):
                getfile = False
    except:
        # Date format not recognized. Need to read all files
        getfile = True 

    fh = open(filename, 'rt')

    if getfile:  
        datablogstarts = False
        for line in fh:
            if line.isspace():
                # blank line
                continue
            elif line.startswith(' '):
                continue
            elif line.startswith('[TSF-file]'):
                contline = line.split()
                stream.header['DataFormat'] = contline[1]
            elif line.startswith('[TIMEFORMAT]'):
                contline = line.split()
                val = contline[1]
            elif line.startswith('[INCREMENT]'):
                contline = line.split()
                stream.header['DataSamplingRate'] = contline[1]
            elif line.startswith('[CHANNELS]'):
                #line = fh.readline()
                #while not line.startswith('['):
                #    # eventually do ot like that
                #    
                #CO:SG025:Grav-1 
                #CO:SG025:Grav-2 
                #CO:SG025:Baro-1 
                #CO:SG025:Baro-2
                pass
            elif line.startswith('[UNITS]'):
                #VOLT
                #VOLT
                #mbar
                #mbar
                pass
            elif line.startswith('[UNDETVAL]'):
                pass
            elif line.startswith('[PHASE_LAG_1_DEG_CPD]'):
                #0.0390
                pass
            elif line.startswith('[PHASE_LAG_1_DEG_CPD_ERROR]'):
                #0.0001
                pass
            elif line.startswith('[N_LATITUDE_DEG]'):
                #47.9288
                contline = line.split()
                stream.header['DataAcquisitionLatitude'] = contline[1]
            elif line.startswith('[N_LATITUDE_DEG_ERROR]'):
                #0.0005
                pass
            elif line.startswith('[E_LONGITUDE_DEG]') :
                #015.8609
                contline = line.split()
                stream.header['DataAcquisitionLongitude'] = contline[1]
            elif line.startswith('[E_LONGITUDE_DEG_ERROR]'):
                #0.0005
                pass
            elif line.startswith('[HEIGHT_M_1]'):
                #1045.00
                contline = line.split()
                stream.header['DataElevation'] = contline[1]
            elif line.startswith('[HEIGHT_M_1_ERROR]'):
                #0.10
                pass
            elif line.startswith('[GRAVITY_CAL_1_UGAL_V]'):
                #-77.8279
                contline = line.split()
                stream.header['DataScaleX'] = contline[1]
            elif line.startswith('[GRAVITY_CAL_1_UGAL_V_ERROR]'):
                #0.5000
                pass
            elif line.startswith('[PRESSURE_CAL_MBAR_V]'):
                #1.0000
                contline = line.split()
                stream.header['DataScaleY'] = contline[1]
            elif line.startswith('[PRESSURE_CAL_MBAR_V_ERROR]'):
                #0.0001
                pass
            elif line.startswith('[AUTHOR]'):
                #(bruno.meurers@univie.ac.at)
                contline = line.split()
                stream.header['SensorDecription'] = contline[1]
            elif line.startswith('[PHASE_LAG_2_DEG_CPD]'):
                #0.0000
                pass
            elif line.startswith('[PHASE_LAG_2_DEG_CPD_ERROR]'):
                #0.0000
                pass
            elif line.startswith('[HEIGHT_M_2]'):
                #00.00
                pass
            elif line.startswith('[HEIGHT_M_2_ERROR]'):
                #0.00
                pass
            elif line.startswith('[GRAVITY_CAL_2_UGAL_V]'):
                #-77.8279
                contline = line.split()
                stream.header['DataScaleZ'] = contline[1]
            elif line.startswith('[GRAVITY_CAL_2_UGAL_V_ERROR]'):
                #0.5000
                pass
            elif line.startswith('[PRESSURE_ADMIT_HPA_NMS2]'):
                #03.5300
                pass
            elif line.startswith('[PRESSURE_MEAN_HPA]'):
                #1000.0
                pass
            elif line.startswith('[COMMENT]'):
                pass
                #SG CT-025 Moved from Vienna to Conrad Observatory 2007/11/07
                #Institute of Meteorology and Geophysics Vienna, Austria
                #Instrument owner Central Institute for Meteorology and Geodynamics
                #Geology Limestone
                #Calibration method LSQ fit to absolute gravity measurements
                #Installation by Eric Brinton (GWR) November 7, 2007
                #Installation Team N.Blaumoser, S.Haden, P.Melichar, B.Meurers, R.Steiner
                #Maintenance by N.Blaumoser, M.Goeschke, S.Haden, B.Meurers
                #date           time       Grav_1     Grav_2    Baro_1    Baro_2
            elif line.startswith('[DATA]'):
                datablogstarts = True
                if headonly:
                    # skip data for option headonly
                    return stream
            else:
                if datablogstarts:
                    # Read data - select according to channels 
                    colsstr = line.split()
                    row = LineStruct()
                    datatime = colsstr[0]+'-'+colsstr[1]+'-'+colsstr[2]+'T'+colsstr[3]+':'+colsstr[4]+':'+colsstr[5]
                    row.time = date2num(datetime.strptime(datatime,"%Y-%m-%dT%H:%M:%S"))
                    row.x = float(colsstr[6])
                    row.y = float(colsstr[7])
                    row.z = float(colsstr[8])
                    row.f = float(colsstr[9])
                    stream.add(row)
                else:
                    # some header lines not noted above found
                    pass

    fh.close()
    return stream


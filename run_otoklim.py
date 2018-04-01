import os 
import sys
import csv
import shutil
import datetime
import qgis.utils

from osgeo import gdal, ogr, osr
from gdalconst import GA_ReadOnly
from qgis.core import *
from qgis.gui import QgsMapCanvas, QgsLayerTreeMapCanvasBridge

from PyQt4.QtCore import *
from PyQt4.QtXml import QDomDocument
from PyQt4.QtGui import *


# Xvfb :99 -ac -noreset & 
# export DISPLAY=:99
# subprocess.call(['sudo', 'python', 'run_otoklim.py']) 
qgisprefix = '/usr'

# configure paths for QGIS 
sys.path.insert(0, qgisprefix+'/share/qgis/python')
sys.path.insert(1, qgisprefix+'/share/qgis/python/plugins')

# disable QGIS debug messages 
os.environ["QT_QPA_PLATFORM"] = "offscreen"

# configure QGIS paths 
QgsApplication.setPrefixPath(qgisprefix, True) 

# initalise QGIS
app = QgsApplication([], True) 
app.initQgis()

# processing modue initialize
from processing.core.Processing import Processing

Processing.initialize()

from processing.tools import general


# Help Function
def create_or_replace(file):
    """Create new or replace existing directory"""
    if os.path.exists(file):
        print '- Replace directory: %s' % file
        shutil.rmtree(file)
        os.mkdir(file)
    else:
        print '- Create directory: %s' % file
        os.mkdir(file)

def check_shp(file, type):
    """Validate input shapefile"""
    print '- Validating shapefile: %s' % file
    if not os.path.exists(file):
        errormessage = 'File is not exist in the path specified: ' + file
        raise Exception(errormessage)
    layer = QgsVectorLayer(file, str(type), 'ogr')
    fields = layer.pendingFields()
    # CRS must be WGS '84 (ESPG=4326)
    if layer.crs().authid().split(':')[1] != '4326':
        errormessage = 'Data Coordinate Reference System must be WGS 1984 (ESPG=4326)'
        raise Exception(errormessage)
    field_names = [field.name() for field in fields]
    field_types = [field.typeName() for field in fields]
    # Field checking
    fieldlist = [
        {'ADM_REGION': 'String'}, {'PROVINSI': 'String'}, {'ID_PROV': 'Real'},
        {'KABUPATEN': 'String'}, {'ID_KAB': 'Real'}, {'KECAMATAN': 'String'},
        {'ID_KEC': 'Real'}, {'DESA': 'String'}, {'ID_DES': 'Real'}
    ]
    if type == 'province':
        checkfield = fieldlist[0:2]
    elif type == 'districts':
        checkfield = fieldlist[0:4]
    elif type == 'subdistricts':
        checkfield = fieldlist[0:6]
    else:
        checkfield = fieldlist
    for field in checkfield:
        if field.keys()[0] not in field_names:
            errormessage = field.keys()[0] + ' field is not exists on data attribute'
            raise Exception(errormessage)
        else:
            idx = field_names.index(field.keys()[0])
            if field_types[idx] != field.values()[0]:
                errormessage = field.keys()[0] + ' field type must be ' + field.values()[0] + ' value'
                raise Exception(errormessage)

def check_raster(file):
    """Validate input raster"""
    print '- Validating raster: %s' % file
    # CRS must be WGS '84 (ESPG=4326)
    read_raster = gdal.Open(file, GA_ReadOnly)
    prj = read_raster.GetProjection()
    srs=osr.SpatialReference(wkt=prj)
    if srs.IsProjected:
        espg = srs.GetAttrValue('AUTHORITY', 1)
    if espg != '4326':
        errormessage = 'Data Coordinate Reference System must be WGS 1984 (ESPG=4326)'
        raise Exception(errormessage)

def check_csv(file, delimiter, type):
    """Validate input CSV"""
    print '- Validating csv file: %s' % file
    # Check csv file header
    with open(file, 'rb') as csvfile:
        spamreader = csv.reader(csvfile, delimiter=str(delimiter), quotechar='|')
        header = spamreader.next()
        error_field = None
        error_field_param = None
        if type == 'rainpost':
            if 'post_id' not in header:
                error_field = 'post_id'
            elif 'city_dist' not in header:
                error_field = 'city_dist'
            elif 'name' not in header:
                error_field = 'name'
            elif 'lat' not in header:
                error_field = 'lat'
            elif 'lon' not in header:
                error_field = 'lon'
        elif type == 'class':
            if 'lower_limit' not in header:
                error_field = 'lower_limit'
            elif 'upper_limit' not in header:
                error_field = 'upper_limit'
            elif 'new_value' not in header:
                error_field = 'new_value'
            elif 'color' not in header:
                error_field = 'color'
        else:
            if 'post_id' not in header:
                error_field = 'post_id'
            if len(header) < 2:
                error_field = "interpolation's parameters"
            else:
                for param in header[1:]:
                    if param not in ['ACH_1', 'ASH_1', 'PCH_1', 'PSH_1', 'PCH_2', 'PSH_2', 'PCH_3', 'PSH_3']:
                        error_field_param = str(param) + ' unknown parameter' 
        if error_field:
            errormessage = error_field + ' field not exists on file header'
            raise Exception(errormessage)
        if error_field_param:
            errormessage = error_field_param
            raise Exception(errormessage)
    # Check csv value type
    with open(file, 'rb') as csvfile:
        spamreader = csv.DictReader(csvfile, delimiter=str(delimiter), quotechar='|')
        line = 1
        for row in spamreader:
            line += 1
            if type == 'rainpost':
                try:
                    float(row['lat'])
                except:
                    error_message = ': lat [' + row['lat'] + '] value must be float'
                    errormessage = 'error at line: ' + str(line) + error_message
                    raise Exception(errormessage)
                try:
                    float(row['lon'])
                except:
                    error_message = ': lon [' + row['lon'] + '] value must be float'
                    errormessage = 'error at line: ' + str(line) + error_message
                    raise Exception(errormessage)
            elif type == 'class':
                try:
                    int(row['lower_limit'])
                except:
                    if row['lower_limit'] == "*":
                        pass
                    else:
                        error_message = ': lower_limit [' + row['lower_limit'] + '] value must be integer'
                        errormessage = 'error at line: ' + str(line) + error_message
                        raise Exception(errormessage)
                try:
                    float(row['upper_limit'])
                except:
                    if row['upper_limit'] == "*":
                        pass
                    else:
                        error_message = ': upper_limit [' + row['upper_limit'] + '] value must be integer'
                        errormessage = 'error at line: ' + str(line) + error_message
                        raise Exception(errormessage)
                try:
                    float(row['new_value'])
                except:
                    error_message = ': new_value [' + row['new_value'] + '] value must be integer'
                    errormessage = 'error at line: ' + str(line) + error_message
                    raise Exception(errormessage)
                # Special case for hex color
                if len(row['color']) != 7 or row['color'][0] != '#':
                    error_message = ': color [' + row['color'] + '] value must be color hex format'
                    errormessage = 'error at line: ' + str(line) + error_message
                    raise Exception(errormessage)
            else:
                try:
                    if 'ACH_1' in row:
                        if row['ACH_1'].strip() == '':
                            pass
                        else:
                            float(row['ACH_1'])
                except:
                    error_message = ': ACH_1 [' + row['ACH_1'] + '] value must be float'
                    errormessage = 'error at line: ' + str(line) + error_message
                    raise Exception(errormessage)
                try:
                    if 'ASH_1' in row:
                        if row['ASH_1'].strip() == '':
                            pass
                        else:
                            float(row['ASH_1'])
                except:
                    error_message = ': ASH_1 [' + row['ASH_1'] + '] value must be float'
                    errormessage = 'error at line: ' + str(line) + error_message
                    raise Exception(errormessage)
                try:
                    if 'PCH_1' in row:
                        if row['PCH_1'].strip() == '':
                            pass
                        else:
                            float(row['PCH_1'])
                except:
                    error_message = ': PCH_1 [' + row['PCH_1'] + '] value must be float'
                    errormessage = 'error at line: ' + str(line) + error_message
                    raise Exception(errormessage)
                try:
                    if 'PSH_1' in row:
                        if row['PSH_1'].strip() == '':
                            pass
                        else:
                            float(row['PSH_1'])
                except:
                    error_message = ': PSH_1 [' + row['PSH_1'] + '] value must be float'
                    errormessage = 'error at line: ' + str(line) + error_message
                    raise Exception(errormessage)
                try:
                    if 'PCH_2' in row:
                        if row['PCH_2'].strip() == '':
                            pass
                        else:
                            float(row['PCH_2'])
                except:
                    error_message = ': PCH_2 [' + row['PCH_2'] + '] value must be float'
                    errormessage = 'error at line: ' + str(line) + error_message
                    raise Exception(errormessage)
                try:
                    if 'PSH_2' in row:
                        if row['PSH_2'].strip() == '':
                            pass
                        else:
                            float(row['PSH_2'])
                except:
                    error_message = ': PSH_2 [' + row['PSH_2'] + '] value must be float'
                    errormessage = 'error at line: ' + str(line) + error_message
                    raise Exception(errormessage)
                try:
                    if 'PCH_3' in row:
                        if row['PCH_3'].strip() == '':
                            pass
                        else:
                            float(row['PCH_3'])
                except:
                    error_message = ': PCH_3 [' + row['PCH_3'] + '] value must be float'
                    errormessage = 'error at line: ' + str(line) + error_message
                    raise Exception(errormessage)
                try:
                    if 'PSH_3' in row:
                        if row['PSH_3'].strip() == '':
                            pass
                        else:
                            float(row['PSH_3'])
                except:
                    error_message = ': PSH_3 [' + row['PSH_3'] + '] value must be float'
                    errormessage = 'error at line: ' + str(line) + error_message
                    raise Exception(errormessage)    

def copy_file(sourcefile, targetdir, shp):
    """Copy file to created directory"""
    print '- Copying %s into %s' % (sourcefile, targetdir)
    if not os.path.exists(sourcefile):
        errormessage = 'File is not exist in the path specified: ' + sourcefile
        raise Exception(errormessage)
    if shp:
        rmv_ext = os.path.splitext(sourcefile)[0]
        shp_name = os.path.split(rmv_ext)[-1]
        dir_name = os.path.dirname(rmv_ext)
        extlist = []
        for infile in os.listdir(dir_name):
            if os.path.splitext(infile)[0] == shp_name:
                ext = os.path.splitext(infile)[1]
                extlist.append(ext)
        if '.dbf' not in extlist:
            errormessage = '.dbf file not found in shapefile strcuture: ' + sourcefile
            raise Exception(errormessage)
        if '.shx' not in extlist:
            errormessage = '.shx file not found in shapefile strcuture: ' + sourcefile
            raise Exception(errormessage)
        for infile in os.listdir(dir_name):
            if os.path.splitext(infile)[0] == shp_name:
                ext = os.path.splitext(infile)[1]
                extlist.append(ext)
                source_file = os.path.join(dir_name, infile)
                target_file = os.path.join(targetdir, shp_name + ext)
                shutil.copyfile(source_file, target_file)
    else:
        filename = os.path.basename(sourcefile)
        source_file = sourcefile
        target_file = os.path.join(targetdir, filename)
        if source_file != target_file:
            shutil.copyfile(source_file, target_file)
        else:
            pass
    return target_file

def select_date_now(mth, yrs):
    """Select all related date now"""
    print '- Select related date for Month and Year'
    if mth == 1:
        mth_s = '01'
    elif mth == 2:
        mth_s = '02'
    elif mth == 3:
        mth_s = '03'
    elif mth == 4:
        mth_s = '04'
    elif mth == 5:
        mth_s = '05'
    elif mth == 6:
        mth_s = '06'
    elif mth == 7:
        mth_s = '07'
    elif mth == 8:
        mth_s = '08'
    elif mth == 9:
        mth_s = '09'
    elif mth == 10:
        mth_s = '10'
    elif mth == 11:
        mth_s = '11'
    else:
        mth_s = '12'

    month_dict = {
        0: ['DES', 'DESEMBER', '12'],
        1: ['JAN', 'JANUARI', '01'],
        2: ['FEB', 'FEBRUARI', '02'],
        3: ['MAR', 'MARET', '03'],
        4: ['APR', 'APRIL', '04'],
        5: ['MEI', 'MEI', '05'],
        6: ['JUN', 'JUNI', '06'],
        7: ['JUL', 'JULI', '07'],
        8: ['AGT', 'AGUSTUS', '08'],
        9: ['SEP', 'SEPTEMBER', '09'],
        10: ['OKT', 'OKTOBER', '10'],
        11: ['NOV', 'NOVEMBER', '11'],
        12: ['DES', 'DESEMBER', '12'],
        13: ['JAN', 'JANUARI', '01'],
        14: ['FEB', 'FEBRUARI', '02'],
        15: ['MAR', 'MARET', '03'],
        16: ['APR', 'APRIL', '04']
    }
    amth = month_dict[mth-1]
    pmth_1 = month_dict[mth+1]
    pmth_2 = month_dict[mth+2]
    pmth_3 = month_dict[mth+3]
    month_header = [amth, pmth_1, pmth_2, pmth_3, mth_s]

    ayrs = yrs
    pyrs_1 = pyrs_2 = pyrs_3 = yrs
    if mth == 12:
        pyrs_1 = yrs + 1
        pyrs_2 = yrs + 1
        pyrs_3 = yrs + 1
    elif mth == 11:
        pyrs_2 = yrs + 1
        pyrs_3 = yrs + 1
    elif mth == 10:
        pyrs_3 = yrs + 1
    elif mth == 1:
        ayrs = yrs - 1
    years_header = [ayrs, pyrs_1, pyrs_2, pyrs_3, yrs]
    return month_header, years_header

# Main Function
def create_project(
        projectname,
        projectworkspace,
        delimiter,
        shp_prov,
        shp_dis,
        shp_subdis,
        shp_vil,
        raster_bat,
        csv_rainpost,
        csv_rainfall,
        csv_normalrain,
        map_template,
        map_template_1,
        map_template_2):
    """Create new project"""
    try:
        print 'Create New Otoklim Project'
        # Create Root Project Directory
        project_directory = projectworkspace
        create_or_replace(projectworkspace)
        # Processing Folder
        processing_directory = os.path.join(projectworkspace, 'processing')
        create_or_replace(processing_directory)
        # Log Folder
        log_directory = os.path.join(processing_directory, 'log')
        create_or_replace(log_directory)
        # Interpolated & Classified Folder
        interpolated_directory = os.path.join(processing_directory, 'interpolated')
        create_or_replace(interpolated_directory)
        classified_directory = os.path.join(processing_directory, 'classified')
        create_or_replace(classified_directory)
        # Boundary Folder
        boundary_directory = os.path.join(project_directory, 'boundary')
        create_or_replace(boundary_directory)
        # Input Folder
        input_directory = os.path.join(project_directory, 'input')
        create_or_replace(input_directory)
        # Output Folder
        output_directory = os.path.join(project_directory, 'output')
        create_or_replace(output_directory)
        # Map & CSV Folder
        map_directory = os.path.join(output_directory, 'map')
        csv_directory = os.path.join(output_directory, 'csv')
        create_or_replace(map_directory)
        create_or_replace(csv_directory)
        # Copy Province Shapefiles
        check_shp(shp_prov, 'province')
        shpprov = copy_file(shp_prov, boundary_directory, True)
        # Copy Cities\Districts Shapefiles
        check_shp(shp_dis, 'districts')
        shpdis = copy_file(shp_dis, boundary_directory, True)
        # Copy Sub-Districts Shapefiles
        check_shp(shp_subdis, 'subdistricts')
        shpshubdis = copy_file(shp_subdis, boundary_directory, True)
        # Copy Villages Shapefiles 
        check_shp(shp_vil, 'villages')
        shpvil = copy_file(shp_vil, boundary_directory, True)
        # Copy Bathymetry Raster File
        check_raster(raster_bat)
        rasterbat = copy_file(raster_bat, boundary_directory, False)
        # Copy Rainpost CSV File
        check_csv(csv_rainpost, delimiter, 'rainpost')
        csvrainpost = copy_file(csv_rainpost, input_directory, False)
        # Copy Rainfall Classification File
        check_csv(csv_rainfall, delimiter, 'class')
        csvrainfall = copy_file(csv_rainfall, input_directory, False)
        # Copy Normal Rain Classification File
        check_csv(csv_normalrain, delimiter, 'class')
        csvnormalrain = copy_file(csv_normalrain, input_directory, False)
        # Copy Map Template File
        map1 = copy_file(map_template, input_directory, False)
        # Copy Map Template 2 File
        map2 = copy_file(map_template_2, input_directory, False)
        # Copy Map Template 3 File
        map3 = copy_file(map_template_3, input_directory, False)
        # Setup Project Parameter
        print 'Setup project parameter'
        project_parameter = {
            'project_directory': project_directory,
            'processing_directory': processing_directory,
            'log_directory': log_directory,
            'interpolated_directory': interpolated_directory,
            'classified_directory': classified_directory,
            'input_directory': input_directory,
            'output_directory': output_directory,
            'map_directory': map_directory,
            'csv_directory': csv_directory,
            'shp_province': shpprov,
            'shp_districts': shpdis,
            'shp_subdistricts': shpshubdis,
            'shp_villages': shpvil,
            'raster_bathymetry': rasterbat,
            'csv_rainpost': csvrainpost,
            'rainfall_rule': csvrainfall,
            'normalrain_rule': csvnormalrain,
            'map_template_1': map1,
            'map_template_2': map2,
            'map_template_3': map3
        }
        return project_parameter
    except Exception as errormessage:
        print errormessage
        project_parameter = None
        return project_parameter


def interpolate_idw(
        project_parameter,
        csv_delimiter,
        input_value_csv,
        province,
        month,
        year,
        number_of_interpolation,
        power_parameter,
        cell_size,
        param_list):
    """Interpolate IDW"""
    try:
        print 'Interpolate IDW Process'
        driver = ogr.GetDriverByName("ESRI Shapefile")
        file_directory = project_parameter['processing_directory']
        filelist = [f for f in os.listdir(file_directory) if os.path.isfile(os.path.join(file_directory, f))]
        for file in filelist:
            os.remove(os.path.join(file_directory, file))
        delimiter = csv_delimiter
        file_input = input_value_csv
        rainpost_file = project_parameter['csv_rainpost']
        combine_file = os.path.join(file_directory, 'combine.csv')
        # Select Date Now
        date = select_date_now(month, year)
        months = date[0]
        years = date[1]
        check_csv(file_input, delimiter, 'input_value')
        # Combine CSV
        print '- Start Combine CSV'
        dict_input = {}
        dict_station = {}
        with open(file_input, 'rb') as csvfile:
            spamreader = csv.reader(csvfile, delimiter=str(delimiter), quotechar='|')
            n = 0
            for row in spamreader:
                if n != 0:
                    dict_input.update({int(row[0]): row[1:]})
                else:
                    idw_params = row[1:]
                    mo = 0
                    for month in months:
                        if mo == 4:
                            break
                        try:
                            idw_params[n] = idw_params[n].split('_')[0] + '_' + str(month[0])
                        except IndexError:
                            pass
                        try:
                            idw_params[n+1] = idw_params[n+1].split('_')[0] + '_' + str(month[0])
                        except IndexError:
                            pass
                        n += 2
                        mo += 1
                    header_input = idw_params
                n += 1
        with open(rainpost_file, 'rb') as csvfile:
            spamreader = csv.reader(csvfile, delimiter=',', quotechar='|')
            n = 0
            for row in spamreader:
                if n != 0:
                    dict_station.update({int(row[0]): row})
                else:
                    header_station = row
                n += 1
        try:
            combine = {k: dict_station.get(k, []) + dict_input.get(k, []) for k in (dict_station.keys() | dict_input.keys())}
        except:
            combine = {k: dict_station.get(k, []) + dict_input.get(k, []) for k in (dict_station.viewkeys() | dict_input.viewkeys())}
        with open(combine_file, "wb+") as csvfile:
            csv_writer = csv.writer(csvfile, delimiter=str(delimiter))
            csv_writer.writerow(header_station + header_input)
            for row in combine.values():
                csv_writer.writerow(row)

        # CSV To Shapefile
        print '- Convert combine CSV to Shapefile'
        csv_file = combine_file
        for param in idw_params:
            filename_shp = os.path.join(file_directory, 'rainpost_point_' + str(param) + '.shp')
            filename_prj = os.path.join(file_directory, 'rainpost_point_' + str(param) + '.shp')
            data_source = driver.CreateDataSource(filename_shp)
            srs = osr.SpatialReference()
            srs.ImportFromEPSG(4326)
            srs.MorphToESRI()
            prj_file = open(filename_prj, 'w')
            prj_file.write(srs.ExportToWkt())
            prj_file.close()
            filename_shp = filename_shp.encode('utf-8')
            layer = data_source.CreateLayer(filename_shp, srs, ogr.wkbPoint)
            with open(csv_file, 'rb') as csvfile:
                reader = csv.reader(csvfile)
                headers = reader.next()
                n = 0
                hdr = []
                for h in headers:
                    if n <= 2:
                        layer.CreateField(ogr.FieldDefn(h, ogr.OFTString))
                    else:
                        if n > 4:
                            if h == param:
                                layer.CreateField(ogr.FieldDefn(h, ogr.OFTReal))
                            else:
                                hdr.append(h)
                        else:
                            layer.CreateField(ogr.FieldDefn(h, ogr.OFTReal))
                    n += 1
                headers = [h for h in headers if h not in hdr]
            with open(csv_file, 'rb') as csvfile:
                spamreader = csv.DictReader(csvfile, delimiter=str(delimiter), quotechar='|')
                for row in spamreader:
                    create_feature = True
                    point = ogr.Geometry(ogr.wkbPoint)
                    feature = ogr.Feature(layer.GetLayerDefn())
                    point.AddPoint(float(row['lon']), float(row['lat']))
                    for h in headers:
                        if h in header_input:
                            if row[h]:
                                feature.SetField(h, row[h])
                            else:
                                create_feature = False
                        else:
                            feature.SetField(h, row[h])
                    if create_feature:
                        feature.SetGeometry(point)
                        layer.CreateFeature(feature)
            del layer
            data_source.Destroy()

        # Province Polygon Query
        print '- Create Province Polygon Shapefile'
        provinsi_polygon = os.path.join(file_directory, 'provinsi_polygon.shp')
        layer = QgsVectorLayer(project_parameter['shp_province'], 'provinsi', 'ogr')
        exp = "\"PROVINSI\"='{}'".format(str(province).upper())
        it = layer.getFeatures(QgsFeatureRequest(QgsExpression(exp)))
        ids = [i.id() for i in it]
        layer.setSelectedFeatures(ids)
        QgsVectorFileWriter.writeAsVectorFormat(layer, provinsi_polygon, "utf-8", layer.crs(), "ESRI Shapefile", 1)

        # Start Interpolate IDW
        print '- Start Interpolate'
        layer_provinsi = QgsVectorLayer(provinsi_polygon, "lyr", "ogr")
        extent = layer_provinsi.extent()
        noip = float(number_of_interpolation)
        power = float(power_parameter)
        prc_list = []
        if 'ach_1' in param_list:
            prc_list.append(idw_params[0])
        if 'ash_1' in param_list:
            prc_list.append(idw_params[1])
        if 'pch_1' in param_list:
            prc_list.append(idw_params[2])
        if 'psh_1' in param_list:
            prc_list.append(idw_params[3])
        if 'pch_2' in param_list:
            prc_list.append(idw_params[4])
        if 'psh_2' in param_list:
            prc_list.append(idw_params[5])
        if 'pch_3' in param_list:
            prc_list.append(idw_params[6])
        if 'psh_3' in param_list:
            prc_list.append(idw_params[7])
        temp = os.path.join(file_directory, 'tmp_' + '{:%Y%m%d_%H%M%S}'.format(datetime.datetime.now()))
        os.mkdir(temp)
        output_rasters = {}
        for param in prc_list:
            filename_shp = os.path.join(file_directory, 'rainpost_point_' + str(param) + '.shp')
            copy_file(filename_shp, temp, True)
            filename_shp_tmp = os.path.join(temp, 'rainpost_point_' + str(param) + '.shp')
            layer = QgsVectorLayer(filename_shp_tmp, 'layer', 'ogr')
            raster_interpolated = os.path.join(temp, param + '_raster_idw.tif')
            raster_cliped = os.path.join(
                project_parameter['interpolated_directory'],
                'interpolated_' + str(param).lower() + '.tif'
            )
            if os.path.exists(raster_cliped):
                os.remove(raster_cliped)
            print '-- Interpolating for param: %s' % str(param)
            general.runalg(
                'grass7:v.surf.idw',
                layer, noip, power, param, False,
                "%f,%f,%f,%f" % (extent.xMinimum(), extent.xMaximum(), extent.yMinimum(), extent.yMaximum()), cell_size, -1.0, 0.0001,
                raster_interpolated
            )
            print '-- Clipping raster interpolated'
            raster_layer = QgsRasterLayer(raster_interpolated, 'raster')
            mask_layer = QgsVectorLayer(provinsi_polygon, 'mask', 'ogr')
            general.runandload("gdalogr:cliprasterbymasklayer",
                raster_layer,
                mask_layer,
                "-9999",
                False,
                True,
                True,
                5,
                4,
                1,
                6,
                1,
                False,
                0,
                False,
                "",
                raster_cliped)
            output_rasters.update({str(param).lower() : raster_cliped})
        return output_rasters, idw_params
    except Exception as errormessage:
        print errormessage
        output_rasters = None
        return output_rasters

def raster_classify(
        project_parameter,
        interpolated,
        filename_rainfall,
        filename_normalrain,
        csv_delimiter,
        param_list):
    """Classify Raster Interpolated"""
    try:
        print 'Classify Raster Interpolated'
        prc_list = []
        file_directory = project_parameter['processing_directory']
        idw_params = interpolated[1]
        if 'ach_1' in param_list:
            prc_list.append(idw_params[0])
        if 'ash_1' in param_list:
            prc_list.append(idw_params[1])
        if 'pch_1' in param_list:
            prc_list.append(idw_params[2])
        if 'psh_1' in param_list:
            prc_list.append(idw_params[3])
        if 'pch_2' in param_list:
            prc_list.append(idw_params[4])
        if 'psh_2' in param_list:
            prc_list.append(idw_params[5])
        if 'pch_3' in param_list:
            prc_list.append(idw_params[6])
        if 'psh_3' in param_list:
            prc_list.append(idw_params[7])
        # Prepare Classification Rule
        # Rainfall
        output_rainfall = os.path.join(
            project_parameter['processing_directory'],
            'rule_ch.txt'
        )
        if os.path.exists(output_rainfall):
            os.remove(output_rainfall)
        row_keeper = []
        print '- Read classification rule from %s ' % str(filename_rainfall)
        with open(filename_rainfall, 'rb') as csvfile:
            spamreader = csv.DictReader(csvfile, delimiter=',', quotechar='|')
            for row in spamreader:
                row_keeper.append([row['lower_limit'], row['upper_limit'], row['new_value']])
        print '- Write classification rule to %s ' % str(output_rainfall)
        with open(output_rainfall, "wb+") as txtfile:
            txt_writer = csv.writer(txtfile, delimiter=':')
            for row in row_keeper:
                txt_writer.writerow(row)
        # Normal Rain
        output_normalrain = os.path.join(
            project_parameter['processing_directory'],
            'rule_sh.txt'
        )
        if os.path.exists(output_normalrain):
            os.remove(output_normalrain)
        row_keeper = []
        print '- Read classification rule from %s ' % str(filename_normalrain)
        with open(filename_normalrain, 'rb') as csvfile:
            spamreader = csv.DictReader(csvfile, delimiter=',', quotechar='|')
            for row in spamreader:
                row_keeper.append([row['lower_limit'], row['upper_limit'], row['new_value']])
        print '- Write classification rule to %s ' % str(output_normalrain)
        with open(output_normalrain, "wb+") as txtfile:
            txt_writer = csv.writer(txtfile, delimiter=':')
            for row in row_keeper:
                txt_writer.writerow(row)
        # Start Classifying Raster
        print '- Start Classifying Raster'
        output_rasters = {}
        output_vectors = {}
        for param in prc_list:
            raster_classified = os.path.join(
                project_parameter['classified_directory'],
                'classified_' + str(param) + '.tif'
            )
            if os.path.exists(raster_classified):
                os.remove(raster_classified)
            rasterinterpolated = interpolated[0][str(param).lower()]
            provinsi_polygon = os.path.join(file_directory, 'provinsi_polygon.shp')
            layer_provinsi = QgsVectorLayer(provinsi_polygon, "lyr", "ogr")
            extent = layer_provinsi.extent()
            print '-- Classifying for param: %s' % str(param)
            if param[0:3] == 'ach' or param[0:3] == 'pch':
                general.runalg(
                    'grass7:r.recode',
                    rasterinterpolated,
                    output_rainfall,
                    False,
                    "%f,%f,%f,%f" % (extent.xMinimum(), extent.xMaximum(), extent.yMinimum(), extent.yMaximum()),
                    0.001,
                    raster_classified
                )
            else:
                general.runalg(
                    'grass7:r.recode',
                    rasterinterpolated,
                    output_normalrain,
                    False,
                    "%f,%f,%f,%f" % (extent.xMinimum(), extent.xMaximum(), extent.yMinimum(), extent.yMaximum()),
                    0.001,
                    raster_classified
                )
            
            # Raster to Vector Conversion (Special Case)
            vector_classified = os.path.join(
                project_parameter['classified_directory'],
                'classified_' + str(param) + '.shp'
            )
            if os.path.exists(vector_classified):
                QgsVectorFileWriter.deleteShapeFile(vector_classified)
                try:
                    os.remove(os.path.splitext(vector_classified)[0] +  '.cpg')
                except OSError:
                    pass
            # Polygonize
            print '-- Convert to vector polygon'
            general.runalg("gdalogr:polygonize", raster_classified, "DN", vector_classified)

            # Add Attribute
            print '-- Add new attribute'
            layer_vector_classified = QgsVectorLayer(vector_classified, 'vector_classified', 'ogr')
            res = layer_vector_classified.dataProvider().addAttributes(
                [
                    QgsField(str(param)[0:3].upper(), QVariant.String),
                    QgsField('Area', QVariant.Double),
                    QgsField('Percent', QVariant.Double),
                ]
            )
            layer_vector_classified.updateFields()
            # Record Label, Value and Color
            print '-- Record label, value, and color'
            label_value = {}
            if str(param)[0:3].upper() == 'ACH' or str(param)[0:3].upper() == 'PCH':
                color = []
                label = []
                list_value = []
                with open(filename_rainfall, 'rb') as csvfile:
                    spamreader = csv.DictReader(csvfile, delimiter=str(csv_delimiter), quotechar='|')
                    for row in spamreader:
                        if str(row['lower_limit']) == '*':
                            label_str = '< ' + str(row['upper_limit'])
                            label.append(label_str)
                        elif str(row['upper_limit']) == '*':
                            label_str = '> ' + str(row['lower_limit'])
                            label.append(label_str)
                        else:
                            label_str = str(row['lower_limit']) + ' - ' + str(row['upper_limit'])
                            label.append(label_str)
                        color.append(row['color'])
                        list_value.append(row['new_value'])
                        label_value.update({row['new_value']: (label_str, row['color'])})
            else:
                color = []
                label = []
                list_value = []
                with open(filename_normalrain, 'rb') as csvfile:
                    spamreader = csv.DictReader(csvfile, delimiter=str(csv_delimiter), quotechar='|')
                    for row in spamreader:
                        if str(row['lower_limit']) == '*':
                            label_str = '< ' + str(row['upper_limit'])
                            label.append(label_str)
                        elif str(row['upper_limit']) == '*':
                            label_str = '> ' + str(row['lower_limit'])
                            label.append(label_str)
                        else:
                            label_str = str(row['lower_limit']) + ' - ' + str(row['upper_limit'])
                            label.append(label_str)
                        color.append(row['color'])
                        list_value.append(row['new_value'])
                        label_value.update({row['new_value']: (label_str, row['color'])})

            # Set Attribute
            print '-- Set attribute'
            expression = QgsExpression("area(transform($geometry, 'EPSG:4326','EPSG:3857'))")
            index = layer_vector_classified.fieldNameIndex("Area")
            expression.prepare(layer_vector_classified.pendingFields())
            area_all = 0
            features = layer_vector_classified.getFeatures()
            for i in features:
                area_all += expression.evaluate(i)
            layer_vector_classified.startEditing()
            features = layer_vector_classified.getFeatures()
            for i in features:
                layer_vector_classified.changeAttributeValue(
                    i.id(),
                    layer_vector_classified.fieldNameIndex(str(param)[0:3].upper()), 
                    str(label_value[str(i['DN'])][0])
                )
                layer_vector_classified.changeAttributeValue(
                    i.id(),
                    layer_vector_classified.fieldNameIndex('Area'), 
                    expression.evaluate(i)
                )
                layer_vector_classified.changeAttributeValue(
                    i.id(),
                    layer_vector_classified.fieldNameIndex('Percent'), 
                    (expression.evaluate(i) / float(area_all)) * 100
                )
            layer_vector_classified.commitChanges()
            # Render Vector Style
            print '-- Rendering and save style'
            style_file = os.path.join(
                project_parameter['classified_directory'],
                'classified_' + str(param) + '.qml'
            )
            categories = []
            for dn, (label, color) in label_value.items():
                symbol = QgsFillSymbolV2.createSimple({'color': color, 'outline_color': '0,0,0,0', 'outline_width': '0'})
                category = QgsRendererCategoryV2(dn, symbol, label)
                categories.append(category)
            expression = 'DN'
            renderer = QgsCategorizedSymbolRendererV2(expression, categories)
            layer_vector_classified.setRendererV2(renderer)
            layer_vector_classified.saveNamedStyle(style_file)
            # Add to dictionary
            output_rasters.update({str(param).lower() : raster_classified})
            output_vectors.update({str(param).lower() : vector_classified})
        return output_rasters, output_vectors, idw_params
    except Exception as errormessage:
        print errormessage
        return None


def generate_map(

    ):
    """Genetare Map"""
    try:
        print 'Generate Map'
    except Exception as errormessage:
        print errormessage
        return None

        """Function to generate map"""
        prcs_directory = os.path.join(self.otoklimdlg.projectworkspace.text(), 'processing')
        logger = self.logger(prcs_directory)
        logger.info('Generate Map..')
        self.iface.mainWindow().statusBar().showMessage('Generate Map..')
        out_directory = os.path.join(self.otoklimdlg.projectworkspace.text(), 'output')
        map_directory = os.path.join(out_directory, 'map')
        filename_xml = os.path.join(map_directory, 'phb.xml')
        classified_directory = os.path.join(prcs_directory, 'classified')
        date = self.select_date_now()
        date_produced = self.otoklimdlg.Date_Produced.text()
        months = date[0]
        years = date[1]
        items = []
        for index in xrange(self.otoklimdlg.treeWidget_selected_1.topLevelItemCount()):
            items.append(self.otoklimdlg.treeWidget_selected_1.topLevelItem(index))
        slc_id_list = [int(float(i.whatsThis(0).split('|')[1])) for i in items]
        slc_name_list = [str(i.whatsThis(0).split('|')[0]) for i in items]
        slc_nametitle_list = [str(i.whatsThis(0).split('|')[2]) for i in items]
        project = os.path.join(
            self.otoklimdlg.projectworkspace.text(),
            self.otoklimdlg.projectfilename.text()
        )
        try:
            logger.debug('- Listing selected parameter to be processed')
            prc_list = []
            date_list = []
            curah_hujan = ET.Element("curah_hujan")
            forecast = ET.SubElement(curah_hujan, "forecast")
            params = ET.SubElement(curah_hujan, "params")
            # set forecast
            issue = ET.SubElement(forecast, "issue")
            ET.SubElement(issue, "timestamp").text = '{:%Y%m%d%H%M%S}'.format(datetime.datetime.now())
            ET.SubElement(issue, "year").text = str(years[4])
            ET.SubElement(issue, "month").text = str(months[4])
            # set params
            if self.otoklimdlg.ach_1_map.isChecked():
                data = ET.SubElement(params, "data")
                with open(project, 'r') as jsonfile:
                    otoklim_project = json.load(jsonfile)
                    raster_ach_1 = otoklim_project["PROCESSING"]["CLASSIFICATION"]["RASTER_ACH_1"]["NAME"]
                    param = os.path.splitext(raster_ach_1)[0].split('_')[1] + '_' + os.path.splitext(raster_ach_1)[0].split('_')[2]
                    otoklim_project["PROCESSING"]["GENERATE_MAP"]["RASTER_ACH_1"]["REGION_LIST"] = str(slc_id_list)
                    ET.SubElement(data, "param").text = str(param.split('_')[0])
                    ET.SubElement(data, "month").text = str(months[0][2])
                    ET.SubElement(data, "year").text = str(years[0])
                with open(project, 'w') as jsonfile:
                    jsonfile.write(json.dumps(otoklim_project, indent=4))
                prc_list.append([param, raster_ach_1])
                logger.debug('-- ' + str(param) + ' is checked')
                date_list.append([months[0], years[0]])
            if self.otoklimdlg.ash_1_map.isChecked():
                data = ET.SubElement(params, "data")
                with open(project, 'r') as jsonfile:
                    otoklim_project = json.load(jsonfile)
                    raster_ash_1 = otoklim_project["PROCESSING"]["CLASSIFICATION"]["RASTER_ASH_1"]["NAME"]
                    param = os.path.splitext(raster_ash_1)[0].split('_')[1] + '_' + os.path.splitext(raster_ash_1)[0].split('_')[2]
                    otoklim_project["PROCESSING"]["GENERATE_MAP"]["RASTER_ASH_1"]["REGION_LIST"] = str(slc_id_list)
                    ET.SubElement(data, "param").text = str(param.split('_')[0])
                    ET.SubElement(data, "month").text = str(months[0][2])
                    ET.SubElement(data, "year").text = str(years[0])
                with open(project, 'w') as jsonfile:
                    jsonfile.write(json.dumps(otoklim_project, indent=4))
                prc_list.append([param, raster_ash_1])
                logger.debug('-- ' + str(param) + ' is checked')
                date_list.append([months[0], years[0]])
            if self.otoklimdlg.pch_1_map.isChecked():
                data = ET.SubElement(params, "data")
                with open(project, 'r') as jsonfile:
                    otoklim_project = json.load(jsonfile)
                    raster_pch_1 = otoklim_project["PROCESSING"]["CLASSIFICATION"]["RASTER_PCH_1"]["NAME"]
                    param = os.path.splitext(raster_pch_1)[0].split('_')[1] + '_' + os.path.splitext(raster_pch_1)[0].split('_')[2]
                    otoklim_project["PROCESSING"]["GENERATE_MAP"]["RASTER_PCH_1"]["REGION_LIST"] = str(slc_id_list)
                    ET.SubElement(data, "param").text = str(param.split('_')[0])
                    ET.SubElement(data, "month").text = str(months[1][2])
                    ET.SubElement(data, "year").text = str(years[1])
                with open(project, 'w') as jsonfile:
                    jsonfile.write(json.dumps(otoklim_project, indent=4))
                prc_list.append([param, raster_pch_1])
                logger.debug('-- ' + str(param) + ' is checked')
                date_list.append([months[1], years[1]])
            if self.otoklimdlg.psh_1_map.isChecked():
                data = ET.SubElement(params, "data")
                with open(project, 'r') as jsonfile:
                    otoklim_project = json.load(jsonfile)
                    raster_psh_1 = otoklim_project["PROCESSING"]["CLASSIFICATION"]["RASTER_PSH_1"]["NAME"]
                    param = os.path.splitext(raster_psh_1)[0].split('_')[1] + '_' + os.path.splitext(raster_psh_1)[0].split('_')[2]
                    otoklim_project["PROCESSING"]["GENERATE_MAP"]["RASTER_PSH_1"]["REGION_LIST"] = str(slc_id_list)
                    ET.SubElement(data, "param").text = str(param.split('_')[0])
                    ET.SubElement(data, "month").text = str(months[1][2])
                    ET.SubElement(data, "year").text = str(years[1])
                with open(project, 'w') as jsonfile:
                    jsonfile.write(json.dumps(otoklim_project, indent=4))
                prc_list.append([param, raster_psh_1])
                logger.debug('-- ' + str(param) + ' is checked')
                date_list.append([months[1], years[1]])
            if self.otoklimdlg.pch_2_map.isChecked():
                data = ET.SubElement(params, "data")
                with open(project, 'r') as jsonfile:
                    otoklim_project = json.load(jsonfile)
                    raster_pch_2 = otoklim_project["PROCESSING"]["CLASSIFICATION"]["RASTER_PCH_2"]["NAME"]
                    param = os.path.splitext(raster_pch_2)[0].split('_')[1] + '_' + os.path.splitext(raster_pch_2)[0].split('_')[2]
                    otoklim_project["PROCESSING"]["GENERATE_MAP"]["RASTER_PCH_2"]["REGION_LIST"] = str(slc_id_list)
                    ET.SubElement(data, "param").text = str(param.split('_')[0])
                    ET.SubElement(data, "month").text = str(months[2][2])
                    ET.SubElement(data, "year").text = str(years[2])
                with open(project, 'w') as jsonfile:
                    jsonfile.write(json.dumps(otoklim_project, indent=4))
                prc_list.append([param, raster_pch_2])
                logger.debug('-- ' + str(param) + ' is checked')
                date_list.append([months[2], years[2]])
            if self.otoklimdlg.psh_2_map.isChecked():
                data = ET.SubElement(params, "data")
                with open(project, 'r') as jsonfile:
                    otoklim_project = json.load(jsonfile)
                    raster_psh_2 = otoklim_project["PROCESSING"]["CLASSIFICATION"]["RASTER_PSH_2"]["NAME"]
                    param = os.path.splitext(raster_psh_2)[0].split('_')[1] + '_' + os.path.splitext(raster_psh_2)[0].split('_')[2]
                    otoklim_project["PROCESSING"]["GENERATE_MAP"]["RASTER_PSH_2"]["REGION_LIST"] = str(slc_id_list)
                    ET.SubElement(data, "param").text = str(param.split('_')[0])
                    ET.SubElement(data, "month").text = str(months[2][2])
                    ET.SubElement(data, "year").text = str(years[2])
                with open(project, 'w') as jsonfile:
                    jsonfile.write(json.dumps(otoklim_project, indent=4))
                prc_list.append([param, raster_psh_2])
                logger.debug('-- ' + str(param) + ' is checked')
                date_list.append([months[2], years[2]])
            if self.otoklimdlg.pch_3_map.isChecked():
                data = ET.SubElement(params, "data")
                with open(project, 'r') as jsonfile:
                    otoklim_project = json.load(jsonfile)
                    raster_pch_3 = otoklim_project["PROCESSING"]["CLASSIFICATION"]["RASTER_PCH_3"]["NAME"]
                    param = os.path.splitext(raster_pch_3)[0].split('_')[1] + '_' + os.path.splitext(raster_pch_3)[0].split('_')[2]
                    otoklim_project["PROCESSING"]["GENERATE_MAP"]["RASTER_PCH_3"]["REGION_LIST"] = str(slc_id_list)
                    ET.SubElement(data, "param").text = str(param.split('_')[0])
                    ET.SubElement(data, "month").text = str(months[3][2])
                    ET.SubElement(data, "year").text = str(years[3])
                with open(project, 'w') as jsonfile:
                    jsonfile.write(json.dumps(otoklim_project, indent=4))
                prc_list.append([param, raster_pch_3])
                logger.debug('-- ' + str(param) + ' is checked')
                date_list.append([months[3], years[3]])
            if self.otoklimdlg.psh_3_map.isChecked():
                data = ET.SubElement(params, "data")
                with open(project, 'r') as jsonfile:
                    otoklim_project = json.load(jsonfile)
                    raster_psh_3 = otoklim_project["PROCESSING"]["CLASSIFICATION"]["RASTER_PSH_3"]["NAME"]
                    param = os.path.splitext(raster_psh_3)[0].split('_')[1] + '_' + os.path.splitext(raster_psh_3)[0].split('_')[2]
                    otoklim_project["PROCESSING"]["GENERATE_MAP"]["RASTER_PSH_3"]["REGION_LIST"] = str(slc_id_list)
                    ET.SubElement(data, "param").text = str(param.split('_')[0])
                    ET.SubElement(data, "month").text = str(months[3][2])
                    ET.SubElement(data, "year").text = str(years[3])
                with open(project, 'w') as jsonfile:
                    jsonfile.write(json.dumps(otoklim_project, indent=4))
                prc_list.append([param, raster_psh_3])
                logger.debug('-- ' + str(param) + ' is checked')
                date_list.append([months[3], years[3]])
            tree = ET.ElementTree(curah_hujan)
            tree.write(filename_xml, encoding='utf-8', xml_declaration=True)
            logger.info('- Selected parameter :' + str(prc_list))
            # Polygon to Line Conversion
            provinsi_line = os.path.join(prcs_directory, 'provinsi_line.shp')
            if not os.path.exists(provinsi_line):
                logger.debug('- Convert Province Boundary..')
                logger.info('- polygonstolines')
                processing.runandload("qgis:polygonstolines", self.otoklimdlg.province.text(), provinsi_line)
                lineprovince = QgsMapLayerRegistry.instance().mapLayersByName('Lines from polygons')[0]
                QgsMapLayerRegistry.instance().removeMapLayer(lineprovince.id())
            kabupaten_line = os.path.join(prcs_directory, 'kabupaten_line.shp')
            if not os.path.exists(kabupaten_line):
                logger.debug('- Convert Districts Boundary..')
                logger.info('- polygonstolines')
                processing.runandload("qgis:polygonstolines", self.otoklimdlg.districts.text(), kabupaten_line)
                linekabupaten = QgsMapLayerRegistry.instance().mapLayersByName('Lines from polygons')[0]
                QgsMapLayerRegistry.instance().removeMapLayer(linekabupaten.id())
            kecamatan_line = os.path.join(prcs_directory, 'kecamatan_line.shp')
            if not os.path.exists(kecamatan_line):
                logger.debug('- Convert Sub-Districts Boundary..')
                logger.info('- polygonstolines')
                processing.runandload("qgis:polygonstolines", self.otoklimdlg.subdistricts.text(), kecamatan_line)
                linekecamatan = QgsMapLayerRegistry.instance().mapLayersByName('Lines from polygons')[0]
                QgsMapLayerRegistry.instance().removeMapLayer(linekecamatan.id())
            desa_line = os.path.join(prcs_directory, 'desa_line.shp')
            if not os.path.exists(desa_line):
                logger.debug('- Convert Villages Boundary..')
                logger.info('- polygonstolines')
                processing.runandload("qgis:polygonstolines", self.otoklimdlg.villages.text(), desa_line)
                linedesa = QgsMapLayerRegistry.instance().mapLayersByName('Lines from polygons')[0]
                QgsMapLayerRegistry.instance().removeMapLayer(linedesa.id())
            # Start Listing
            for value, date in zip(prc_list, date_list):
                logger.info('-- Field (Parameter) : ' + value[0])
                logger.debug('-- Generate Map in progress...')
                vector_classified = os.path.join(classified_directory, value[1])
                style_file = os.path.join(classified_directory, os.path.splitext(value[1])[0] + '.qml')
                temp_raster = os.path.join(prcs_directory, 'tmp' + str(value[1]))
                if os.path.exists(temp_raster):
                    pass
                else:
                    os.mkdir(temp_raster)
                month = date[0]
                year = date[1]
                for slc_id, slc_name, slc_nametitle in zip(slc_id_list, slc_name_list, slc_nametitle_list):
                    logger.info('--- Region processed : ' + slc_name)
                    projectqgs = os.path.join(prcs_directory, str(slc_name) + '_qgisproject_' + str(value[0]) + '_' + str(slc_id) + '.qgs')
                    output_jpg = os.path.join(map_directory, str(slc_id) + '_' + str(years[4]) + str(months[4]) + '_' + str(year) + str(month[2]) + '_' + str(value[0]).split('_')[0] + '_' + str(slc_name) + '.jpg')
                    if os.path.basename(output_jpg) not in os.listdir(map_directory):
                        if len(str(slc_id)) == 2:
                            # Classified Value Styling
                            layer_vector = QgsVectorLayer(vector_classified, '', 'ogr')
                            layer_vector.loadNamedStyle(style_file)
                            # Province Styling
                            layer_provinsi = QgsVectorLayer(self.otoklimdlg.province.text(), 'Provinsi', 'ogr')
                            exp = "\"ID_PROV\"!='{}'".format(str(slc_id))
                            layer_provinsi.setSubsetString(exp)
                            symbol = QgsFillSymbolV2.createSimple({'color': '169,169,169,255', 'outline_color': '0,0,0,0', 'outline_style': 'solid', 'outline_width': '0.5'})
                            layer_provinsi.rendererV2().setSymbol(symbol)
                            layer_provinsi_line = QgsVectorLayer(provinsi_line, 'Batas Provinsi', 'ogr')
                            symbol = QgsLineSymbolV2.createSimple({'color': '0,0,0,255', 'penstyle': 'solid', 'width': '0.5'})
                            layer_provinsi_line.rendererV2().setSymbol(symbol)
                            layer_provinsi.triggerRepaint()
                            palyr = QgsPalLayerSettings()
                            palyr.readFromLayer(layer_provinsi)
                            palyr.enabled = True
                            palyr.fieldName = 'PROVINSI'
                            palyr.placement = QgsPalLayerSettings.OverPoint
                            palyr.setDataDefinedProperty(QgsPalLayerSettings.Size, True, True, '14', '')
                            palyr.setDataDefinedProperty(QgsPalLayerSettings.BufferDraw, True, True, '1', '')
                            palyr.setDataDefinedProperty(QgsPalLayerSettings.BufferSize, True, True, '1', '')
                            palyr.writeToLayer(layer_provinsi)
                            # Districts Styling
                            layer_kabupaten = QgsVectorLayer(self.otoklimdlg.districts.text(), 'Kabupaten', 'ogr')
                            exp = "\"ID_PROV\"='{}'".format(str(slc_id))
                            layer_kabupaten.setSubsetString(exp)
                            symbol = QgsFillSymbolV2.createSimple({'color': '0,0,0,0', 'outline_color': '0,0,0,0', 'outline_style': 'dot', 'outline_width': '0.25'})
                            layer_kabupaten.rendererV2().setSymbol(symbol)
                            layer_kabupaten_line = QgsVectorLayer(kabupaten_line, 'Batas Kabupaten', 'ogr')
                            layer_kabupaten_line.setSubsetString(exp)
                            symbol = QgsLineSymbolV2.createSimple({'color': '0,0,0,255', 'penstyle': 'dot', 'width': '0.25'})
                            layer_kabupaten_line.rendererV2().setSymbol(symbol)
                            palyr = QgsPalLayerSettings()
                            palyr.readFromLayer(layer_kabupaten)
                            palyr.enabled = True
                            palyr.fieldName = 'KABUPATEN'
                            palyr.placement = QgsPalLayerSettings.OverPoint
                            palyr.setDataDefinedProperty(QgsPalLayerSettings.Size, True, True, '8', '')
                            palyr.setDataDefinedProperty(QgsPalLayerSettings.BufferDraw, True, True, '1', '')
                            palyr.setDataDefinedProperty(QgsPalLayerSettings.BufferSize, True, True, '1', '')
                            palyr.writeToLayer(layer_kabupaten)
                            # Bathymetry
                            layer_bath = QgsRasterLayer(self.otoklimdlg.bathymetry.text(), 'Bathymetry')
                            # Add Layer To QGIS Canvas
                            canvas = qgis.utils.iface.mapCanvas()
                            QgsMapLayerRegistry.instance().addMapLayer(layer_bath)
                            QgsMapLayerRegistry.instance().addMapLayer(layer_provinsi)
                            QgsMapLayerRegistry.instance().addMapLayer(layer_kabupaten)
                            QgsMapLayerRegistry.instance().addMapLayer(layer_vector)
                            QgsMapLayerRegistry.instance().addMapLayer(layer_kabupaten_line)
                            QgsMapLayerRegistry.instance().addMapLayer(layer_provinsi_line)
                            # Set Extent
                            canvas.setExtent(layer_kabupaten.extent())
                            canvas.refresh()
                            # Create QGIS Porject File
                            f = QFileInfo(projectqgs)
                            p = QgsProject.instance()
                            p.write(f)
                            QgsProject.instance().clear()
                            # Read Map
                            template_file = open(self.otoklimdlg.maptemplate.text())
                            template_content = template_file.read()
                            template_file.close()
                            document = QDomDocument()
                            document.setContent(template_content)
                            if str(value[0])[0:3].upper() == 'ACH' or str(value[0])[0:3].upper() == 'PCH':
                                title_type = "CURAH"
                            else:
                                title_type = "SIFAT"
                            if str(value[0])[0:3].upper().startswith('A'):
                                title_adj = "ANALISIS"
                            else:
                                title_adj = "PRAKIRAAN"
                            map_title = 'PETA ' + title_adj + ' ' + title_type + ' HUJAN BULAN ' + str(month[1]) + ' TAHUN '+ str(year) + ' ' + str(slc_nametitle).upper()
                            substitution_map = {'map_title': map_title, 'date_produced':date_produced}
                            canvas = QgsMapCanvas()
                            QgsProject.instance().read(QFileInfo(projectqgs))
                            bridge = QgsLayerTreeMapCanvasBridge(QgsProject.instance().layerTreeRoot(), canvas)
                            bridge.setCanvasLayers()
                            composition = QgsComposition(canvas.mapSettings())
                            composition.loadFromTemplate(document, substitution_map)
                            map_item = composition.getComposerItemById('map')
                            map_item.setMapCanvas(canvas)
                            # Province Polygon As Extent
                            if self.otoklimdlg.province_extent.isChecked():
                                map_item.zoomToExtent(canvas.extent())
                            legend_item = composition.getComposerItemById('legend_line')
                            legend_item.updateLegend()
                            composition.refreshItems()
                            # Save as image
                            dpi = 300
                            dpmm = dpi / 25.4
                            width = int(dpmm * composition.paperWidth())
                            height = int(dpmm * composition.paperHeight())
                            # create output image and initialize it
                            image = QImage(QSize(width, height), QImage.Format_ARGB32)
                            image.setDotsPerMeterX(dpmm * 1000)
                            image.setDotsPerMeterY(dpmm * 1000)
                            image.fill(0)
                            # render the composition
                            imagePainter = QPainter(image)
                            composition.renderPage(imagePainter, 0)
                            imagePainter.end()
                            image.save(output_jpg, "jpg")
                            logger.info('--- Image saved at : ' + output_jpg)
                            # Remove unuse file
                            vector = QgsMapLayerRegistry.instance().mapLayersByName('')[0]
                            kabupaten = QgsMapLayerRegistry.instance().mapLayersByName('Kabupaten')[0]
                            provinsi = QgsMapLayerRegistry.instance().mapLayersByName('Provinsi')[0]
                            bathymetry = QgsMapLayerRegistry.instance().mapLayersByName('Bathymetry')[0]
                            provinsiline = QgsMapLayerRegistry.instance().mapLayersByName('Batas Provinsi')[0]
                            kabupatenline = QgsMapLayerRegistry.instance().mapLayersByName('Batas Kabupaten')[0]
                            all_layer = [vector.id(), kabupaten.id(), provinsi.id(), bathymetry.id(), provinsiline.id(), kabupatenline.id()]
                            QgsMapLayerRegistry.instance().removeMapLayers(all_layer)
                        elif len(str(slc_id)) == 4:
                            # Classified Value Styling
                            layer_vector = QgsVectorLayer(vector_classified, '', 'ogr')
                            layer_vector.loadNamedStyle(style_file)
                            # Province Styling
                            layer_provinsi = QgsVectorLayer(self.otoklimdlg.province.text(), 'Provinsi', 'ogr')
                            symbol = QgsFillSymbolV2.createSimple({'color': '240,240,240,255', 'outline_color': '0,0,0,255', 'outline_style': 'solid', 'outline_width': '0.5'})
                            layer_provinsi.rendererV2().setSymbol(symbol)
                            layer_provinsi.triggerRepaint()
                            # Districts Styling
                            layer_kabupaten = QgsVectorLayer(self.otoklimdlg.districts.text(), 'Kabupaten', 'ogr')
                            exp = "\"ID_PROV\"='{}' AND \"ID_KAB\"!='{}'".format(str(slc_id)[0:2], str(slc_id))
                            layer_kabupaten.setSubsetString(exp)
                            symbol = QgsFillSymbolV2.createSimple({'color': '169,169,169,255', 'outline_color': '0,0,0,0', 'outline_style': 'solid', 'outline_width': '0.5'})
                            layer_kabupaten.rendererV2().setSymbol(symbol)
                            layer_kabupaten.triggerRepaint()
                            layer_kabupaten_line = QgsVectorLayer(kabupaten_line, 'Batas Kabupaten', 'ogr')
                            layer_kabupaten_line.setSubsetString(exp)
                            symbol = QgsLineSymbolV2.createSimple({'color': '0,0,0,255', 'penstyle': 'solid', 'width': '0.5'})
                            layer_kabupaten_line.rendererV2().setSymbol(symbol)
                            palyr = QgsPalLayerSettings()
                            palyr.readFromLayer(layer_kabupaten)
                            palyr.enabled = True
                            palyr.fieldName = 'KABUPATEN'
                            palyr.placement = QgsPalLayerSettings.OverPoint
                            palyr.setDataDefinedProperty(QgsPalLayerSettings.Size, True, True, '14', '')
                            palyr.setDataDefinedProperty(QgsPalLayerSettings.BufferDraw, True, True, '1', '')
                            palyr.setDataDefinedProperty(QgsPalLayerSettings.BufferSize, True, True, '1', '')
                            palyr.writeToLayer(layer_kabupaten)
                            # Sub-Districts Styling
                            layer_kecamatan = QgsVectorLayer(self.otoklimdlg.subdistricts.text(), 'Kecamatan', 'ogr')
                            exp = "\"ID_KAB\"='{}'".format(str(slc_id))
                            layer_kecamatan.setSubsetString(exp)
                            symbol = QgsFillSymbolV2.createSimple({'color': '0,0,0,0', 'outline_color': '0,0,0,0', 'outline_style': 'dot', 'outline_width': '0.25'})
                            layer_kecamatan.rendererV2().setSymbol(symbol)
                            layer_kecamatan_line = QgsVectorLayer(kecamatan_line, 'Batas Kecamatan', 'ogr')
                            layer_kecamatan_line.setSubsetString(exp)
                            symbol = QgsLineSymbolV2.createSimple({'color': '0,0,0,255', 'penstyle': 'dot', 'width': '0.25'})
                            layer_kecamatan_line.rendererV2().setSymbol(symbol)
                            palyr = QgsPalLayerSettings()
                            palyr.readFromLayer(layer_kecamatan)
                            palyr.enabled = True
                            palyr.fieldName = 'KECAMATAN'
                            palyr.placement = QgsPalLayerSettings.OverPoint
                            palyr.setDataDefinedProperty(QgsPalLayerSettings.Size, True, True, '8', '')
                            palyr.setDataDefinedProperty(QgsPalLayerSettings.BufferDraw, True, True, '1', '')
                            palyr.setDataDefinedProperty(QgsPalLayerSettings.BufferSize, True, True, '1', '')
                            palyr.writeToLayer(layer_kecamatan)
                            # Bathymetry
                            layer_bath = QgsRasterLayer(self.otoklimdlg.bathymetry.text(), 'Bathymetry')
                            # Add Layer To QGIS Canvas
                            canvas = qgis.utils.iface.mapCanvas()
                            QgsMapLayerRegistry.instance().addMapLayer(layer_bath)
                            QgsMapLayerRegistry.instance().addMapLayer(layer_provinsi)
                            QgsMapLayerRegistry.instance().addMapLayer(layer_vector)
                            QgsMapLayerRegistry.instance().addMapLayer(layer_kabupaten)    
                            QgsMapLayerRegistry.instance().addMapLayer(layer_kecamatan)
                            QgsMapLayerRegistry.instance().addMapLayer(layer_kecamatan_line)
                            QgsMapLayerRegistry.instance().addMapLayer(layer_kabupaten_line)
                            # Set Extent
                            canvas.setExtent(layer_kecamatan.extent())
                            canvas.refresh()
                            # Create QGIS Porject File
                            f = QFileInfo(projectqgs)
                            p = QgsProject.instance()
                            p.write(f)
                            QgsProject.instance().clear()
                            QgsMapLayerRegistry.instance().removeMapLayer(layer_vector.id())
                            del layer_vector
                            # Read Map
                            template_file = open(self.otoklimdlg.maptemplate2.text())
                            template_content = template_file.read()
                            template_file.close()
                            document = QDomDocument()
                            document.setContent(template_content)
                            if str(value[0])[0:3].upper() == 'ACH' or str(value[0])[0:3].upper() == 'PCH':
                                title_type = "CURAH"
                            else:
                                title_type = "SIFAT"
                            if str(value[0])[0:3].upper().startswith('A'):
                                title_adj = "ANALISIS"
                            else:
                                title_adj = "PRAKIRAAN"
                            map_title = 'PETA ' + title_adj + ' ' + title_type + ' HUJAN BULAN ' + str(month[1]) + ' TAHUN '+ str(year) + ' ' + str(slc_nametitle).upper()
                            substitution_map = {'map_title': map_title, 'date_produced':date_produced}
                            canvas = QgsMapCanvas()
                            QgsProject.instance().read(QFileInfo(projectqgs))
                            bridge = QgsLayerTreeMapCanvasBridge(QgsProject.instance().layerTreeRoot(), canvas)
                            bridge.setCanvasLayers()
                            composition = QgsComposition(canvas.mapSettings())
                            composition.loadFromTemplate(document, substitution_map)
                            map_item = composition.getComposerItemById('map')
                            map_item.setMapCanvas(canvas)
                            map_item.zoomToExtent(canvas.extent())
                            composition.refreshItems()
                            # Save as image
                            dpi = 200
                            dpmm = dpi / 25.4
                            width = int(dpmm * composition.paperWidth())
                            height = int(dpmm * composition.paperHeight())
                            # create output image and initialize it
                            image = QImage(QSize(width, height), QImage.Format_ARGB32)
                            image.setDotsPerMeterX(dpmm * 1000)
                            image.setDotsPerMeterY(dpmm * 1000)
                            image.fill(0)
                            # render the composition
                            imagePainter = QPainter(image)
                            composition.renderPage(imagePainter, 0)
                            imagePainter.end()
                            image.save(output_jpg, "jpg")
                            logger.info('--- Image saved at : ' + output_jpg)
                            # Remove unuse file
                            vector = QgsMapLayerRegistry.instance().mapLayersByName('')[0]
                            kecamatan = QgsMapLayerRegistry.instance().mapLayersByName('Kecamatan')[0]
                            kabupaten = QgsMapLayerRegistry.instance().mapLayersByName('Kabupaten')[0]
                            provinsi = QgsMapLayerRegistry.instance().mapLayersByName('Provinsi')[0]
                            bathymetry = QgsMapLayerRegistry.instance().mapLayersByName('Bathymetry')[0]
                            kabupatenline = QgsMapLayerRegistry.instance().mapLayersByName('Batas Kabupaten')[0]
                            kecamatanline = QgsMapLayerRegistry.instance().mapLayersByName('Batas Kecamatan')[0]
                            all_layer = [vector.id(), kabupaten.id(), provinsi.id(), bathymetry.id(), kecamatan.id(), kabupatenline.id(), kecamatanline.id()]
                            QgsMapLayerRegistry.instance().removeMapLayers(all_layer)
                            del vector
                            os.remove(projectqgs)
                        else:
                            # Classified Value Styling
                            layer_vector = QgsVectorLayer(vector_classified, '', 'ogr')
                            layer_vector.loadNamedStyle(style_file)
                            # Province Styling
                            layer_provinsi = QgsVectorLayer(self.otoklimdlg.province.text(), 'Provinsi', 'ogr')
                            symbol = QgsFillSymbolV2.createSimple({'color': '240,240,240,255', 'outline_color': '0,0,0,255', 'outline_style': 'solid', 'outline_width': '0.5'})
                            layer_provinsi.rendererV2().setSymbol(symbol)
                            layer_provinsi.triggerRepaint()
                            # Districts Styling
                            layer_kabupaten = QgsVectorLayer(self.otoklimdlg.districts.text(), 'Kabupaten', 'ogr')
                            exp = "\"ID_PROV\"='{}' AND \"ID_KAB\"!='{}'".format(str(slc_id)[0:2], str(slc_id)[0:4])
                            layer_kabupaten.setSubsetString(exp)
                            symbol = QgsFillSymbolV2.createSimple({'color': '223,223,223,255', 'outline_color': '0,0,0,255', 'outline_style': 'solid', 'outline_width': '0.5'})
                            layer_kabupaten.rendererV2().setSymbol(symbol)
                            layer_kabupaten.triggerRepaint()
                            # Sub-Districts Styling
                            layer_kecamatan = QgsVectorLayer(self.otoklimdlg.subdistricts.text(), 'Kecamatan', 'ogr')
                            exp = "\"ID_KAB\"='{}' AND \"ID_KEC\"!='{}'".format(str(slc_id)[0:4], str(slc_id))
                            layer_kecamatan.setSubsetString(exp)
                            symbol = QgsFillSymbolV2.createSimple({'color': '169,169,169,255', 'outline_color': '0,0,0,0', 'outline_style': 'solid', 'outline_width': '0.5'})
                            layer_kecamatan.rendererV2().setSymbol(symbol)
                            layer_kecamatan.triggerRepaint()
                            layer_kecamatan_line = QgsVectorLayer(kecamatan_line, 'Batas Kecamatan', 'ogr')
                            layer_kecamatan_line.setSubsetString(exp)
                            symbol = QgsLineSymbolV2.createSimple({'color': '0,0,0,255', 'penstyle': 'solid', 'width': '0.5'})
                            layer_kecamatan_line.rendererV2().setSymbol(symbol)
                            palyr = QgsPalLayerSettings()
                            palyr.readFromLayer(layer_kecamatan)
                            palyr.enabled = True
                            palyr.fieldName = 'KECAMATAN'
                            palyr.placement = QgsPalLayerSettings.OverPoint
                            palyr.setDataDefinedProperty(QgsPalLayerSettings.Size, True, True, '14', '')
                            palyr.setDataDefinedProperty(QgsPalLayerSettings.BufferDraw, True, True, '1', '')
                            palyr.setDataDefinedProperty(QgsPalLayerSettings.BufferSize, True, True, '1', '')
                            palyr.writeToLayer(layer_kecamatan)
                            # Villages Styling
                            layer_desa = QgsVectorLayer(self.otoklimdlg.villages.text(), 'Desa', 'ogr')
                            exp = "\"ID_KEC\"='{}'".format(str(slc_id))
                            layer_desa.setSubsetString(exp)
                            symbol = QgsFillSymbolV2.createSimple({'color': '0,0,0,0', 'outline_color': '0,0,0,0', 'outline_style': 'dot', 'outline_width': '0.25'})
                            layer_desa.rendererV2().setSymbol(symbol)
                            layer_desa_line = QgsVectorLayer(desa_line, 'Batas Desa', 'ogr')
                            layer_desa_line.setSubsetString(exp)
                            symbol = QgsLineSymbolV2.createSimple({'color': '0,0,0,255', 'penstyle': 'dot', 'width': '0.25'})
                            layer_desa_line.rendererV2().setSymbol(symbol)
                            palyr = QgsPalLayerSettings()
                            palyr.readFromLayer(layer_desa)
                            palyr.enabled = True
                            palyr.fieldName = 'DESA'
                            palyr.placement = QgsPalLayerSettings.OverPoint
                            palyr.setDataDefinedProperty(QgsPalLayerSettings.Size, True, True, '8', '')
                            palyr.setDataDefinedProperty(QgsPalLayerSettings.BufferDraw, True, True, '1', '')
                            palyr.setDataDefinedProperty(QgsPalLayerSettings.BufferSize, True, True, '1', '')
                            palyr.writeToLayer(layer_desa)
                            # Bathymetry
                            layer_bath = QgsRasterLayer(self.otoklimdlg.bathymetry.text(), 'Bathymetry')
                            # Add Layer To QGIS Canvas
                            canvas = qgis.utils.iface.mapCanvas()
                            QgsMapLayerRegistry.instance().addMapLayer(layer_bath)
                            QgsMapLayerRegistry.instance().addMapLayer(layer_provinsi)
                            QgsMapLayerRegistry.instance().addMapLayer(layer_vector)
                            QgsMapLayerRegistry.instance().addMapLayer(layer_kabupaten)
                            QgsMapLayerRegistry.instance().addMapLayer(layer_kecamatan)
                            QgsMapLayerRegistry.instance().addMapLayer(layer_desa)
                            QgsMapLayerRegistry.instance().addMapLayer(layer_desa_line)
                            QgsMapLayerRegistry.instance().addMapLayer(layer_kecamatan_line)
                            # Set Extent
                            canvas.setExtent(layer_desa.extent())
                            canvas.refresh()
                            # Create QGIS Porject File
                            f = QFileInfo(projectqgs)
                            p = QgsProject.instance()
                            p.write(f)
                            QgsProject.instance().clear()
                            QgsMapLayerRegistry.instance().removeMapLayer(layer_vector.id())
                            del layer_vector
                            # Read Map
                            template_file = open(self.otoklimdlg.maptemplate3.text())
                            template_content = template_file.read()
                            template_file.close()
                            document = QDomDocument()
                            document.setContent(template_content)
                            if str(value[0])[0:3].upper() == 'ACH' or str(value[0])[0:3].upper() == 'PCH':
                                title_type = "CURAH"
                            else:
                                title_type = "SIFAT"
                            if str(value[0])[0:3].upper().startswith('A'):
                                title_adj = "ANALISIS"
                            else:
                                title_adj = "PRAKIRAAN"
                            map_title = 'PETA ' + title_adj + ' ' + title_type + ' HUJAN BULAN ' + str(month[1]) + ' TAHUN '+ str(year) + ' ' + str(slc_nametitle).upper()
                            substitution_map = {'map_title': map_title, 'date_produced':date_produced}
                            canvas = QgsMapCanvas()
                            QgsProject.instance().read(QFileInfo(projectqgs))
                            bridge = QgsLayerTreeMapCanvasBridge(QgsProject.instance().layerTreeRoot(), canvas)
                            bridge.setCanvasLayers()
                            composition = QgsComposition(canvas.mapSettings())
                            composition.loadFromTemplate(document, substitution_map)
                            map_item = composition.getComposerItemById('map')
                            map_item.setMapCanvas(canvas)
                            map_item.zoomToExtent(canvas.extent())
                            composition.refreshItems()
                            # Save as image
                            dpi = 150
                            dpmm = dpi / 25.4
                            width = int(dpmm * composition.paperWidth())
                            height = int(dpmm * composition.paperHeight())
                            # create output image and initialize it
                            image = QImage(QSize(width, height), QImage.Format_ARGB32)
                            image.setDotsPerMeterX(dpmm * 1000)
                            image.setDotsPerMeterY(dpmm * 1000)
                            image.fill(0)
                            # render the composition
                            imagePainter = QPainter(image)
                            composition.renderPage(imagePainter, 0)
                            imagePainter.end()
                            image.save(output_jpg, "jpg")
                            logger.info('--- Image saved at : ' + output_jpg)
                            # Remove unuse file
                            vector = QgsMapLayerRegistry.instance().mapLayersByName('')[0]
                            desa = QgsMapLayerRegistry.instance().mapLayersByName('Desa')[0]
                            kecamatan = QgsMapLayerRegistry.instance().mapLayersByName('Kecamatan')[0]
                            kabupaten = QgsMapLayerRegistry.instance().mapLayersByName('Kabupaten')[0]
                            provinsi = QgsMapLayerRegistry.instance().mapLayersByName('Provinsi')[0]
                            bathymetry = QgsMapLayerRegistry.instance().mapLayersByName('Bathymetry')[0]
                            kecamatanline = QgsMapLayerRegistry.instance().mapLayersByName('Batas Kecamatan')[0]
                            desaline = QgsMapLayerRegistry.instance().mapLayersByName('Batas Desa')[0]
                            all_layer = [vector.id(), desa.id(), kabupaten.id(), provinsi.id(), bathymetry.id(), kecamatan.id(), kecamatanline.id(), desaline.id()]
                            QgsMapLayerRegistry.instance().removeMapLayers(all_layer)
                            del vector
                            os.remove(projectqgs)
                    else:
                        logger.info('--- Skip processing for ' + str(os.path.basename(output_jpg)))
                        pass
                shutil.rmtree(temp_raster)
                self.otoklimdlg.showGenerateMapFolder.setEnabled(True)
        except Exception as e:
            self.errormessagedlg.ErrorMessage.setText(str(e))
            logger.error(str(e))
            self.errormessagedlg.exec_()











   




# Files Storage Path & Folder
currentpath = os.path.dirname(os.path.abspath(__file__))
filepath = 'sample_files'
projectpath = 'dirproject'

# Project Parameter
project_name = 'jatim_ch'
project_workspace = os.path.join(currentpath, projectpath, project_name)
csv_delimiter = ','
province_shp = os.path.join(currentpath, filepath, 'Admin_Provinsi_BPS2013_GEO.shp')
districts_shp = os.path.join(currentpath, filepath, 'Admin_Kabupaten_BPS2013_GEO.shp')
subdistricts_shp = os.path.join(currentpath, filepath, 'Admin_Kecamatan_BPS2013_GEO.shp')
village_shp = os.path.join(currentpath, filepath, 'Admin_Desa_BPS2013_GEO.shp')
bathymetry = os.path.join(currentpath, filepath, 'byth_gebco_invert.tif')
rainpost_file = os.path.join(currentpath, filepath, 'rainpost_jatim.csv')
rainfall_class = os.path.join(currentpath, filepath, 'rule_ch.csv')
normalrain_class = os.path.join(currentpath, filepath, 'rule_sh.csv')
map_template_1 = os.path.join(currentpath, filepath, 'template/jatim_ch.qpt')
map_template_2 = os.path.join(currentpath, filepath, 'template/jatim_umum_ch.qpt')
map_template_3 = os.path.join(currentpath, filepath, 'template/jatim_umum_ch.qpt')

# Interpolation Parameter
input_value_csv = os.path.join(currentpath, filepath, 'input_sample_jatim.csv')
province = 'Jawa Timur'
month = 3
year = 2018
number_of_interpolation = 8.0
power_parameter = 5.0
cell_size = 0.001
param_list = ['ach_1', 'ash_1', 'pch_1', 'psh_1', 'pch_2', 'psh_2', 'pch_3', 'psh_3']
#param_list = ['psh_3']
filename_rainfall = os.path.join(currentpath, filepath, 'rule_ch.csv')
filename_normalrain = os.path.join(currentpath, filepath, 'rule_sh.csv')


if __name__ == '__main__':
    project_parameter = create_project(
        project_name,
        project_workspace,
        csv_delimiter,
        province_shp,
        districts_shp,
        subdistricts_shp,
        village_shp,
        bathymetry,
        rainpost_file,
        rainfall_class,
        normalrain_class,
        map_template_1,
        map_template_2,
        map_template_3
    )
    if project_parameter:
        interpolated = interpolate_idw(
            project_parameter,
            csv_delimiter,
            input_value_csv,
            province,
            month,
            year,
            number_of_interpolation,
            power_parameter,
            cell_size,
            param_list
        )
    else:
        interpolated = None

    if interpolated and project_parameter:
        classified = raster_classify(
            project_parameter,
            interpolated,
            filename_rainfall,
            filename_normalrain,
            csv_delimiter,
            param_list
        )
    else:
        classified = None







































































    

def classify():
    from processing.core.Processing import Processing

    Processing.initialize()

    from processing.tools import general

    provinsi_polygon_file = os.path.join(currentpath, filepath, 'provinsi_polygon.shp')
    layer_provinsi = QgsVectorLayer(provinsi_polygon_file, 'layer', 'ogr')
    extent = layer_provinsi.extent()

    raster_classified = os.path.join(currentpath, filepath, 'raster_classified.tif')
    rasterinterpolated = os.path.join(currentpath, filepath, 'interpolated_cliped.tif')

    output_rainfall = os.path.join(currentpath, filepath, 'rule_ch.txt')

    general.runalg(
        'grass7:r.recode',
        rasterinterpolated,
        output_rainfall,
        False,
        "%f,%f,%f,%f" % (extent.xMinimum(), extent.xMaximum(), extent.yMinimum(), extent.yMaximum()),
        0.001,
        raster_classified
    )



def generate_map():
    vector_classified = os.path.join(currentpath, filepath, 'classified_ach_nov.shp')
    style_file = os.path.join(currentpath, filepath, 'classified_ach_nov.qml')
    provinsi_line = os.path.join(currentpath, filepath, 'provinsi_line.shp')
    kabupaten_line = os.path.join(currentpath, filepath, 'kabupaten_line.shp')

    province_file = os.path.join(currentpath, filepath, 'main', 'Admin_Provinsi_BPS2013_GEO.shp')
    slc_id = 35
    districts_file = os.path.join(currentpath, filepath, 'main', 'Admin_Kabupaten_BPS2013_GEO.shp')
    bathymetry_file = os.path.join(currentpath, filepath, 'main', 'byth_gebco_invert.tif')
    map_template = os.path.join(currentpath, filepath, 'main', 'template', 'jatim_ch.qpt')
    northarrow = os.path.join(currentpath, filepath, 'main', 'northarrow.PNG')
    legenda_ch_landscape = os.path.join(currentpath, filepath, 'main', 'legenda_ch_landscape.PNG')
    logo = os.path.join(currentpath, filepath, 'main', 'logo_jatim.png')
    inset = os.path.join(currentpath, filepath, 'main', 'jatim_inset.png')

    projectqgs = os.path.join(currentpath, filepath, 'qgisproject.qgs')
    output_jpg = os.path.join(currentpath, filepath, 'map_ach.jpg')

    # Classified Value Styling
    layer_vector = QgsVectorLayer(vector_classified, '', 'ogr')
    layer_vector.loadNamedStyle(style_file)
    # Province Styling
    layer_provinsi = QgsVectorLayer(province_file, 'Provinsi', 'ogr')
    exp = "\"ID_PROV\"!='{}'".format(str(slc_id))
    layer_provinsi.setSubsetString(exp)
    symbol = QgsFillSymbolV2.createSimple({'color': '169,169,169,255', 'outline_color': '0,0,0,0', 'outline_style': 'solid', 'outline_width': '0.5'})
    layer_provinsi.rendererV2().setSymbol(symbol)
    layer_provinsi_line = QgsVectorLayer(provinsi_line, 'Batas Provinsi', 'ogr')
    symbol = QgsLineSymbolV2.createSimple({'color': '0,0,0,255', 'penstyle': 'solid', 'width': '0.5'})
    layer_provinsi_line.rendererV2().setSymbol(symbol)
    layer_provinsi.triggerRepaint()
    palyr = QgsPalLayerSettings()
    palyr.readFromLayer(layer_provinsi)
    palyr.enabled = True
    palyr.fieldName = 'PROVINSI'
    palyr.placement = QgsPalLayerSettings.OverPoint
    palyr.setDataDefinedProperty(QgsPalLayerSettings.Size, True, True, '14', '')
    palyr.setDataDefinedProperty(QgsPalLayerSettings.BufferDraw, True, True, '1', '')
    palyr.setDataDefinedProperty(QgsPalLayerSettings.BufferSize, True, True, '1', '')
    palyr.writeToLayer(layer_provinsi)
    # Districts Styling
    layer_kabupaten = QgsVectorLayer(districts_file, 'Kabupaten', 'ogr')
    exp = "\"ID_PROV\"='{}'".format(str(slc_id))
    layer_kabupaten.setSubsetString(exp)
    symbol = QgsFillSymbolV2.createSimple({'color': '0,0,0,0', 'outline_color': '0,0,0,0', 'outline_style': 'dot', 'outline_width': '0.25'})
    layer_kabupaten.rendererV2().setSymbol(symbol)
    layer_kabupaten_line = QgsVectorLayer(kabupaten_line, 'Batas Kabupaten', 'ogr')
    layer_kabupaten_line.setSubsetString(exp)
    symbol = QgsLineSymbolV2.createSimple({'color': '0,0,0,255', 'penstyle': 'dot', 'width': '0.25'})
    layer_kabupaten_line.rendererV2().setSymbol(symbol)
    palyr = QgsPalLayerSettings()
    palyr.readFromLayer(layer_kabupaten)
    palyr.enabled = True
    palyr.fieldName = 'KABUPATEN'
    palyr.placement = QgsPalLayerSettings.OverPoint
    palyr.setDataDefinedProperty(QgsPalLayerSettings.Size, True, True, '8', '')
    palyr.setDataDefinedProperty(QgsPalLayerSettings.BufferDraw, True, True, '1', '')
    palyr.setDataDefinedProperty(QgsPalLayerSettings.BufferSize, True, True, '1', '')
    palyr.writeToLayer(layer_kabupaten)
    # Bathymetry
    layer_bath = QgsRasterLayer(bathymetry_file, 'Bathymetry')
    # Add Layer To QGIS Canvas
    print "Add Layer"
    canvas = QgsMapCanvas()
    QgsMapLayerRegistry.instance().addMapLayer(layer_bath)
    QgsMapLayerRegistry.instance().addMapLayer(layer_provinsi)
    QgsMapLayerRegistry.instance().addMapLayer(layer_kabupaten)
    QgsMapLayerRegistry.instance().addMapLayer(layer_vector)
    QgsMapLayerRegistry.instance().addMapLayer(layer_kabupaten_line)
    QgsMapLayerRegistry.instance().addMapLayer(layer_provinsi_line)
    # Set Extent
    print "Set Extent"
    canvas.setExtent(layer_kabupaten.extent())
    canvas.refresh()
    # Create QGIS Porject File
    print "Create QGIS Project"
    f = QFileInfo(projectqgs)
    p = QgsProject.instance()
    p.write(f)
    QgsProject.instance().clear()
    # Read Map
    print "Read Map"
    template_file = open(map_template)
    template_content = template_file.read()
    template_file.close()
    document = QDomDocument()
    document.setContent(template_content)
    '''
    if str(value[0])[0:3].upper() == 'ACH' or str(value[0])[0:3].upper() == 'PCH':
        title_type = "CURAH"
    else:
        title_type = "SIFAT"
    if str(value[0])[0:3].upper().startswith('A'):
        title_adj = "ANALISIS"
    else:
        title_adj = "PRAKIRAAN"
    '''
    title_type = "CURAH"
    title_adj = "ANALISIS"
    map_title = 'PETA ' + title_adj + ' ' + title_type + ' HUJAN BULAN '
    date_produced = '???'
    substitution_map = {'map_title': map_title, 'date_produced':date_produced}
    canvas = QgsMapCanvas()
    QgsProject.instance().read(QFileInfo(projectqgs))
    bridge = QgsLayerTreeMapCanvasBridge(QgsProject.instance().layerTreeRoot(), canvas)
    bridge.setCanvasLayers()
    composition = QgsComposition(canvas.mapSettings())
    composition.loadFromTemplate(document, substitution_map)
    map_item = composition.getComposerItemById('map')
    map_item.setMapCanvas(canvas)
    # Set Image
    northarrow_item = composition.getComposerItemById('northarrow')
    northarrow_item.setPictureFile(northarrow)
    legenda_ch_landscape_item = composition.getComposerItemById('legenda')
    legenda_ch_landscape_item.setPictureFile(legenda_ch_landscape)
    logo_item = composition.getComposerItemById('logo')
    logo_item.setPictureFile(logo)
    inset_item = composition.getComposerItemById('inset')
    inset_item.setPictureFile(inset)
    # Province Polygon As Extent
    '''
    if self.otoklimdlg.province_extent.isChecked():
        map_item.zoomToExtent(canvas.extent())
    '''
    legend_item = composition.getComposerItemById('legend_line')
    legend_item.updateLegend()
    composition.refreshItems()
    # Save as image
    dpi = 300
    dpmm = dpi / 25.4
    width = int(dpmm * composition.paperWidth())
    height = int(dpmm * composition.paperHeight())
    # create output image and initialize it
    image = QImage(QSize(width, height), QImage.Format_ARGB32)
    image.setDotsPerMeterX(dpmm * 1000)
    image.setDotsPerMeterY(dpmm * 1000)
    image.fill(0)
    # render the composition
    imagePainter = QPainter(image)
    composition.renderPage(imagePainter, 0)
    imagePainter.end()
    image.save(output_jpg, "jpg")

    # Remove unuse file
    vector = QgsMapLayerRegistry.instance().mapLayersByName('')[0]
    kabupaten = QgsMapLayerRegistry.instance().mapLayersByName('Kabupaten')[0]
    provinsi = QgsMapLayerRegistry.instance().mapLayersByName('Provinsi')[0]
    bathymetry = QgsMapLayerRegistry.instance().mapLayersByName('Bathymetry')[0]
    provinsiline = QgsMapLayerRegistry.instance().mapLayersByName('Batas Provinsi')[0]
    kabupatenline = QgsMapLayerRegistry.instance().mapLayersByName('Batas Kabupaten')[0]
    all_layer = [vector.id(), kabupaten.id(), provinsi.id(), bathymetry.id(), provinsiline.id(), kabupatenline.id()]
    QgsMapLayerRegistry.instance().removeMapLayers(all_layer)



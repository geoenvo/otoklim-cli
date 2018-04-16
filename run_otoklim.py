import argparse
import os
import psycopg2
import json
import sys
import csv
import shutil
import logging
import datetime
import qgis.utils
import xml.etree.cElementTree as ET
import zipfile
import ast
import geoserver.util

from osgeo import gdal, ogr, osr
from gdalconst import GA_ReadOnly
from qgis.core import *
from qgis.gui import QgsMapCanvas, QgsLayerTreeMapCanvasBridge

from geoserver.catalog import Catalog

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
def logger(prc_dir):
    """Function to trigger python logging"""
    print "Create logging function"
    log_dir = os.path.join(prc_dir, 'log')
    log_filename = os.path.join(log_dir, 'otoklim_' + '{:%Y%m%d_%H%M%S}'.format(datetime.datetime.now()) + '.log')
    try:
        os.remove(log_filename)
    except OSError:
        pass
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    fh = logging.FileHandler(log_filename)
    formatter = logging.Formatter("%(asctime)s - [%(levelname)s] %(message)s")
    ch.setFormatter(formatter)
    fh.setFormatter(formatter)
    logger.addHandler(ch)
    logger.addHandler(fh)
    logger.info('Running start at ' + '{:%Y-%m-%d %H:%M:%S}'.format(datetime.datetime.now()))
    return logger

def create_or_replace(file):
    """Create new or replace existing directory"""
    if os.path.exists(file):
        print '- Replace directory: %s' % file
        shutil.rmtree(file)
        os.mkdir(file)
    else:
        print '- Create directory: %s' % file
        os.mkdir(file)

def unzip_shp(shp_unzip):
    """Unzip Shapefile file"""
    print '- Unzip shapefile : %s' % str(shp_unzip)
    extract_dir = os.path.splitext(str(shp_unzip))[0]
    if os.path.exists(extract_dir):
        shutil.rmtree(extract_dir)
        os.mkdir(extract_dir)
    zip_ref = zipfile.ZipFile(shp_unzip, 'r')
    zip_ref.extractall(extract_dir)
    zip_ref.close()
    shapefile = None
    for zfile in os.listdir(extract_dir):
        if str(os.path.splitext(zfile)[1]).lower() == ".shp":
            shapefile = os.path.join(extract_dir, zfile)
    if shapefile == None:
        errormessage = 'Shapefile (.shp) is not exist in the path specified: ' + extract_dir
        raise Exception(errormessage)
    else:
        return shapefile

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

def selected_region_format(slc_region):
    """Formating Selected Region"""
    print '- Formating Selected Region'
    region_formated = []
    if type(slc_region) == str:
        slc_region = ast.literal_eval(slc_region)
    for region in slc_region:
        if str(region[1]).upper() == "PROVINSI":
            region_formated.append([
                str(region[0]),
                str(region[2]),
                str(region[1]) + ' '+ str(region[0])
            ])
        elif str(region[1]).upper() == "KABUPATEN":
            region_formated.append([
                str(region[0]),
                str(region[2]),
                'KAB. ' + str(region[0]) + ', PROV. ' + str(region[3])
            ])
        elif str(region[1]).upper() == "KOTA":
            region_formated.append([
                str(region[0]),
                str(region[2]),
                'KOTA ' + str(region[0]) + ', PROV. ' + str(region[3])
            ])
        else:
            region_formated.append([
                str(region[0]),
                str(region[2]),
                'KEC. ' + str(region[0]) + ', KAB. ' + str(region[3]) + ', PROV. ' + str(region[4])
            ])
    return region_formated


# Main Function
def create_project(
        table_name,
        cur,
        conn,
        id_value,
        projectname,
        projectworkspace,
        delimiter,
        shp_prov_zipped,
        shp_dis_zipped,
        shp_subdis_zipped,
        shp_vil_zipped,
        raster_bat,
        csv_rainpost,
        csv_rainfall,
        csv_normalrain,
        map_template,
        map_template_1,
        map_template_2):
    """Create new project"""
    try:
        # Create Root Project Directory
        project_directory = projectworkspace
        create_or_replace(projectworkspace)
        # Processing Folder
        processing_directory = os.path.join(projectworkspace, 'processing')
        create_or_replace(processing_directory)
        # Log Folder
        log_directory = os.path.join(processing_directory, 'log')
        create_or_replace(log_directory)
        # Logging Start Here
        log = logger(processing_directory)
        log.info('Create New Otoklim Project')
        output_log = ""
        output_log += 'Create New Otoklim Project \n'
        query = (
            "UPDATE " + table_name +
            " SET output_log = %s "
            " WHERE id = %s "
        )
        data = (str(output_log), str(id_value))
        cur.execute(query, data)
        conn.commit()
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
        shp_prov = unzip_shp(shp_prov_zipped)
        check_shp(shp_prov, 'province')
        shpprov = copy_file(shp_prov, boundary_directory, True)
        # Copy Cities\Districts Shapefiles
        shp_dis = unzip_shp(shp_dis_zipped)
        check_shp(shp_dis, 'districts')
        shpdis = copy_file(shp_dis, boundary_directory, True)
        # Copy Sub-Districts Shapefiles
        shp_subdis = unzip_shp(shp_subdis_zipped)
        check_shp(shp_subdis, 'subdistricts')
        shpshubdis = copy_file(shp_subdis, boundary_directory, True)
        # Copy Villages Shapefiles 
        shp_vil = unzip_shp(shp_vil_zipped)
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
        log.info('Setup project parameter')
        output_log += 'Setup project parameter \n'
        query = (
            "UPDATE " + table_name +
            " SET output_log = %s "
            " WHERE id = %s "
        )
        data = (str(output_log), str(id_value))
        cur.execute(query, data)
        conn.commit()
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
            'map_template_3': map3,
            'log': log,
            'output_log': output_log
        }
        return project_parameter
    except Exception as errormessage:
        log.error(errormessage)
        output_log += errormessage + '\n'
        query = (
            "UPDATE " + table_name +
            " SET output_log = %s "
            " WHERE id = %s "
        )
        data = (str(output_log), str(id_value))
        cur.execute(query, data)
        conn.commit()
        project_parameter = None
        return project_parameter


def interpolate_idw(
        table_name,
        cur,
        conn,
        id_value,
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
        output_log = project_parameter['output_log']
        log = project_parameter['log']
        log.info('Interpolate IDW Process')
        output_log += 'Interpolate IDW Process \n'
        query = (
            "UPDATE " + table_name +
            " SET output_log = %s "
            " WHERE id = %s "
        )
        data = (str(output_log), str(id_value))
        cur.execute(query, data)
        conn.commit()
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
        log.info('- Start Combine CSV')
        output_log += '- Start Combine CSV \n'
        query = (
            "UPDATE " + table_name +
            " SET output_log = %s "
            " WHERE id = %s "
        )
        data = (str(output_log), str(id_value))
        cur.execute(query, data)
        conn.commit()
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
        log.info('- Convert combine CSV to Shapefile')
        output_log += '- Convert combine CSV to Shapefile \n'
        query = (
            "UPDATE " + table_name +
            " SET output_log = %s "
            " WHERE id = %s "
        )
        data = (str(output_log), str(id_value))
        cur.execute(query, data)
        conn.commit()
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
        log.info('- Create Province Polygon Shapefile')
        output_log += '- Create Province Polygon Shapefile \n'
        query = (
            "UPDATE " + table_name +
            " SET output_log = %s "
            " WHERE id = %s "
        )
        data = (str(output_log), str(id_value))
        cur.execute(query, data)
        conn.commit()
        provinsi_polygon = os.path.join(file_directory, 'provinsi_polygon.shp')
        layer = QgsVectorLayer(project_parameter['shp_province'], 'provinsi', 'ogr')
        exp = "\"PROVINSI\"='{}'".format(str(province).upper())
        it = layer.getFeatures(QgsFeatureRequest(QgsExpression(exp)))
        ids = [i.id() for i in it]
        layer.setSelectedFeatures(ids)
        QgsVectorFileWriter.writeAsVectorFormat(layer, provinsi_polygon, "utf-8", layer.crs(), "ESRI Shapefile", 1)

        # Start Interpolate IDW
        log.info('- Start Interpolate')
        output_log += '- Start Interpolate \n'
        query = (
            "UPDATE " + table_name +
            " SET output_log = %s "
            " WHERE id = %s "
        )
        data = (str(output_log), str(id_value))
        cur.execute(query, data)
        conn.commit()
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
            log.info('-- Interpolating for param: %s' % str(param))
            output_log += '-- Interpolating for param: %s' % str(param) + ' \n'
            query = (
                "UPDATE " + table_name +
                " SET output_log = %s "
                " WHERE id = %s "
            )
            data = (str(output_log), str(id_value))
            cur.execute(query, data)
            conn.commit()
            general.runalg(
                'grass7:v.surf.idw',
                layer, noip, power, param, False,
                "%f,%f,%f,%f" % (extent.xMinimum(), extent.xMaximum(), extent.yMinimum(), extent.yMaximum()), cell_size, -1.0, 0.0001,
                raster_interpolated
            )
            log.info('-- Clipping raster interpolated')
            output_log += '-- Clipping raster interpolated \n'
            query = (
                "UPDATE " + table_name +
                " SET output_log = %s "
                " WHERE id = %s "
            )
            data = (str(output_log), str(id_value))
            cur.execute(query, data)
            conn.commit()
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
        return output_rasters, idw_params, output_log
    except Exception as errormessage:
        log.error(errormessage)
        output_log += errormessage + '\n'
        query = (
            "UPDATE " + table_name +
            " SET output_log = %s "
            " WHERE id = %s "
        )
        data = (str(output_log), str(id_value))
        cur.execute(query, data)
        conn.commit()
        output_rasters = None
        return output_rasters

def raster_classify(
        table_name,
        cur,
        conn,
        id_value,
        project_parameter,
        interpolated,
        filename_rainfall,
        filename_normalrain,
        csv_delimiter,
        param_list):
    """Classify Raster Interpolated"""
    try:
        log = project_parameter['log']
        log.info('Classify Raster Interpolated')
        output_log = interpolated[2]
        output_log += 'Classify Raster Interpolated \n'
        query = (
            "UPDATE " + table_name +
            " SET output_log = %s "
            " WHERE id = %s "
        )
        data = (str(output_log), str(id_value))
        cur.execute(query, data)
        conn.commit()
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
        log.info('- Read classification rule from %s ' % str(filename_rainfall))
        output_log += '- Read classification rule from %s ' % str(filename_rainfall) + ' \n'
        query = (
            "UPDATE " + table_name +
            " SET output_log = %s "
            " WHERE id = %s "
        )
        data = (str(output_log), str(id_value))
        cur.execute(query, data)
        conn.commit()
        with open(filename_rainfall, 'rb') as csvfile:
            spamreader = csv.DictReader(csvfile, delimiter=',', quotechar='|')
            for row in spamreader:
                row_keeper.append([row['lower_limit'], row['upper_limit'], row['new_value']])
        log.info('- Write classification rule to %s ' % str(output_rainfall))
        output_log += '- Write classification rule to %s ' % str(output_rainfall) + ' \n'
        query = (
            "UPDATE " + table_name +
            " SET output_log = %s "
            " WHERE id = %s "
        )
        data = (str(output_log), str(id_value))
        cur.execute(query, data)
        conn.commit()
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
        log.info('- Read classification rule from %s ' % str(filename_normalrain))
        output_log += '- Read classification rule from %s ' % str(filename_normalrain) + ' \n' 
        query = (
            "UPDATE " + table_name +
            " SET output_log = %s "
            " WHERE id = %s "
        )
        data = (str(output_log), str(id_value))
        cur.execute(query, data)
        conn.commit()
        with open(filename_normalrain, 'rb') as csvfile:
            spamreader = csv.DictReader(csvfile, delimiter=',', quotechar='|')
            for row in spamreader:
                row_keeper.append([row['lower_limit'], row['upper_limit'], row['new_value']])
        log.info('- Write classification rule to %s ' % str(output_normalrain))
        output_log += '- Write classification rule to %s ' % str(output_normalrain) + ' \n'
        query = (
            "UPDATE " + table_name +
            " SET output_log = %s "
            " WHERE id = %s "
        )
        data = (str(output_log), str(id_value))
        cur.execute(query, data)
        conn.commit()
        with open(output_normalrain, "wb+") as txtfile:
            txt_writer = csv.writer(txtfile, delimiter=':')
            for row in row_keeper:
                txt_writer.writerow(row)
        # Start Classifying Raster
        log.info('- Start Classifying Raster')
        output_log += '- Start Classifying Raster \n'
        query = (
            "UPDATE " + table_name +
            " SET output_log = %s "
            " WHERE id = %s "
        )
        data = (str(output_log), str(id_value))
        cur.execute(query, data)
        conn.commit()
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
            log.info('-- Classifying for param: %s' % str(param))
            output_log += '-- Classifying for param: %s' % str(param) + ' \n'  
            query = (
                "UPDATE " + table_name +
                " SET output_log = %s "
                " WHERE id = %s "
            )
            data = (str(output_log), str(id_value))
            cur.execute(query, data)
            conn.commit()
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
            log.info('-- Convert to vector polygon')
            output_log += '-- Convert to vector polygon \n'
            query = (
                "UPDATE " + table_name +
                " SET output_log = %s "
                " WHERE id = %s "
            )
            data = (str(output_log), str(id_value))
            cur.execute(query, data)
            conn.commit()
            general.runalg("gdalogr:polygonize", raster_classified, "DN", vector_classified)

            # Add Attribute
            log.info('-- Add new attribute')
            output_log += '-- Add new attribute \n'
            query = (
                "UPDATE " + table_name +
                " SET output_log = %s "
                " WHERE id = %s "
            )
            data = (str(output_log), str(id_value))
            cur.execute(query, data)
            conn.commit()
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
            log.info('-- Record label, value, and color')
            output_log += '-- Record label, value, and color \n'
            query = (
                "UPDATE " + table_name +
                " SET output_log = %s "
                " WHERE id = %s "
            )
            data = (str(output_log), str(id_value))
            cur.execute(query, data)
            conn.commit()
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
            log.info('-- Set attribute')
            output_log += '-- Set attribute \n'
            query = (
                "UPDATE " + table_name +
                " SET output_log = %s "
                " WHERE id = %s "
            )
            data = (str(output_log), str(id_value))
            cur.execute(query, data)
            conn.commit()
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
            log.info('-- Rendering and save style')
            output_log += '-- Rendering and save style \n'
            query = (
                "UPDATE " + table_name +
                " SET output_log = %s "
                " WHERE id = %s "
            )
            data = (str(output_log), str(id_value))
            cur.execute(query, data)
            conn.commit()
            style_file_qml = os.path.join(
                project_parameter['classified_directory'],
                'classified_' + str(param) + '.qml'
            )
            style_file_sld = os.path.join(
                project_parameter['classified_directory'],
                'classified_' + str(param) + '.sld'
            )
            categories = []
            for dn, (label, color) in label_value.items():
                symbol = QgsFillSymbolV2.createSimple({'color': color, 'outline_color': '0,0,0,0', 'outline_width': '0'})
                category = QgsRendererCategoryV2(dn, symbol, label)
                categories.append(category)
            expression = 'DN'
            renderer = QgsCategorizedSymbolRendererV2(expression, categories)
            layer_vector_classified.setRendererV2(renderer)
            layer_vector_classified.saveNamedStyle(style_file_qml)
            layer_vector_classified.saveSldStyle(style_file_sld)
            # Add to dictionary
            output_rasters.update({str(param).lower() : raster_classified})
            output_vectors.update({str(param).lower() : vector_classified})
        return output_rasters, output_vectors, idw_params, output_log
    except Exception as errormessage:
        log.error(errormessage)
        output_log += errormessage + '\n'
        query = (
            "UPDATE " + table_name +
            " SET output_log = %s "
            " WHERE id = %s "
        )
        data = (str(output_log), str(id_value))
        cur.execute(query, data)
        conn.commit()
        return None


def push_to_geoserver(
        gs_url,
        gs_username,
        gs_password,
        project_name,
        otoklim_site,
        project_parameter,
        classified
    ):
    """Push to Geoserver"""
    try:
        log = project_parameter['log']
        log.info('Push Classified Shp to GeoServer')
        output_log = classified[3]
        output_log += 'Push Classified Shp to GeoServer \n'
        query = (
            "UPDATE " + table_name +
            " SET output_log = %s "
            " WHERE id = %s "
        )
        data = (str(output_log), str(id_value))
        cur.execute(query, data)
        conn.commit()
        shp_dir = project_parameter["classified_directory"]
        cat = Catalog(
            gs_url,
            username= gs_username,
            password= gs_password
        )
        # Create Workspace
        workspacename = 'otoklim_' + project_name
        try:
            log.info("- Create Otoklim Workspace")
            output_log += '- Create Otoklim Workspace \n'
            query = (
                "UPDATE " + table_name +
                " SET output_log = %s "
                " WHERE id = %s "
            )
            data = (str(output_log), str(id_value))
            cur.execute(query, data)
            conn.commit()
            ws = cat.create_workspace(workspacename, otoklim_site)
        except:
            log.info("- Skip.. Otoklim workspace already created")
            output_log += '- Skip.. Otoklim workspace already created \n'
            query = (
                "UPDATE " + table_name +
                " SET output_log = %s "
                " WHERE id = %s "
            )
            data = (str(output_log), str(id_value))
            cur.execute(query, data)
            conn.commit()
            ws = cat.get_workspace(workspacename)
        # Create Feature Store
        log.info("- Create Feature Store")
        output_log += '- Create Feature Store \n'
        query = (
            "UPDATE " + table_name +
            " SET output_log = %s "
            " WHERE id = %s "
        )
        data = (str(output_log), str(id_value))
        cur.execute(query, data)
        conn.commit()
        shp_list = [shp.split(".")[0] for shp in os.listdir(shp_dir)]
        for shp in list(set(shp_list)):
            shp_path = os.path.join(shp_dir, shp)
            classified_file = geoserver.util.shapefile_and_friends(shp_path)
            # Create Feature Store
            try:
                log.info("-- Create feature store for : %s" % shp)
                output_log += '-- Create feature store for : %s \n' % shp
                query = (
                    "UPDATE " + table_name +
                    " SET output_log = %s "
                    " WHERE id = %s "
                )
                data = (str(output_log), str(id_value))
                cur.execute(query, data)
                conn.commit()
                cat.create_featurestore(str(shp), classified_file, ws)
                sldfile = shp_path + ".sld"
                with open(sldfile) as f:
                    cat.create_style(str(shp), f.read(), overwrite=True, style_format="sld11")
                layer = cat.get_layer("%s:%s" % (workspacename, str(shp)))
                layer._set_default_style(str(shp))
                cat.save(layer)
            except:
                log.info("-- %s store already exists" % shp)
                output_log += '-- %s store already exists \n' % shp
                query = (
                    "UPDATE " + table_name +
                    " SET output_log = %s "
                    " WHERE id = %s "
                )
                data = (str(output_log), str(id_value))
                cur.execute(query, data)
                conn.commit()
        return output_log
    except Exception as errormessage:
        log.error(errormessage)
        output_log += errormessage + '\n'
        query = (
            "UPDATE " + table_name +
            " SET output_log = %s "
            " WHERE id = %s "
        )
        data = (str(output_log), str(id_value))
        cur.execute(query, data)
        conn.commit()
        return None

def generate_map(
        output_log,
        table_name,
        cur,
        conn,
        id_value,
        project_parameter,
        classified,
        month,
        year,
        param_list,
        selected_region,
        map_template_1,
        map_template_2,
        map_template_3,
        date_produced,
        northarrow,
        legenda_ch,
        legenda_sh,
        logo,
        inset,
    ):
    """Genetare Map"""
    try:
        log = project_parameter['log']
        log.info('Generate Map')
        output_log += 'Generate Map \n'
        query = (
            "UPDATE " + table_name +
            " SET output_log = %s "
            " WHERE id = %s "
        )
        data = (str(output_log), str(id_value))
        cur.execute(query, data)
        conn.commit()
        file_directory = project_parameter['project_directory']
        prcs_directory = project_parameter['processing_directory']
        out_directory = project_parameter['output_directory']
        map_directory = project_parameter['map_directory']
        filename_xml = os.path.join(map_directory, 'phb.xml')
        classified_directory = project_parameter['classified_directory']
        # Spatial File
        province_shp = project_parameter['shp_province']
        districts_shp = project_parameter['shp_districts']
        subdistricts_shp = project_parameter['shp_subdistricts']
        village_shp = project_parameter['shp_villages']
        bathymetry_raster = project_parameter['raster_bathymetry']
        date = select_date_now(month, year)
        months = date[0]
        years = date[1]
        # Create PHB XML
        log.info('- Create PHB XML')
        output_log += '- Create PHB XML \n'
        query = (
            "UPDATE " + table_name +
            " SET output_log = %s "
            " WHERE id = %s "
        )
        data = (str(output_log), str(id_value))
        cur.execute(query, data)
        conn.commit()
        curah_hujan = ET.Element("curah_hujan")
        forecast = ET.SubElement(curah_hujan, "forecast")
        params = ET.SubElement(curah_hujan, "params")
        issue = ET.SubElement(forecast, "issue")
        ET.SubElement(issue, "timestamp").text = '{:%Y%m%d%H%M%S}'.format(datetime.datetime.now())
        ET.SubElement(issue, "year").text = str(years[4])
        ET.SubElement(issue, "month").text = str(months[4])
        prc_list = []
        date_list = []
        idw_params = classified[2]
        vector_classified = classified[1]
        raster_classified = classified[0]
        if 'ach_1' in param_list:
            prc_list.append([idw_params[0], vector_classified[str(idw_params[0]).lower()]])
            date_list.append([months[0], years[0]])
            data = ET.SubElement(params, "data")
            ET.SubElement(data, "param").text = str(idw_params[0].split('_')[0])
            ET.SubElement(data, "month").text = str(months[0][2])
            ET.SubElement(data, "year").text = str(years[0])
        if 'ash_1' in param_list:
            prc_list.append([idw_params[1], vector_classified[str(idw_params[1]).lower()]])
            date_list.append([months[0], years[0]])
            data = ET.SubElement(params, "data")
            ET.SubElement(data, "param").text = str(idw_params[0].split('_')[0])
            ET.SubElement(data, "month").text = str(months[0][2])
            ET.SubElement(data, "year").text = str(years[0])
        if 'pch_1' in param_list:
            prc_list.append([idw_params[2], vector_classified[str(idw_params[2]).lower()]])
            date_list.append([months[1], years[1]])
            data = ET.SubElement(params, "data")
            ET.SubElement(data, "param").text = str(idw_params[0].split('_')[0])
            ET.SubElement(data, "month").text = str(months[1][2])
            ET.SubElement(data, "year").text = str(years[1])
        if 'psh_1' in param_list:
            prc_list.append([idw_params[3], vector_classified[str(idw_params[3]).lower()]])
            date_list.append([months[1], years[1]])
            data = ET.SubElement(params, "data")
            ET.SubElement(data, "param").text = str(idw_params[0].split('_')[0])
            ET.SubElement(data, "month").text = str(months[1][2])
            ET.SubElement(data, "year").text = str(years[1])
        if 'pch_2' in param_list:
            prc_list.append([idw_params[4], vector_classified[str(idw_params[4]).lower()]])
            date_list.append([months[2], years[2]])
            data = ET.SubElement(params, "data")
            ET.SubElement(data, "param").text = str(idw_params[0].split('_')[0])
            ET.SubElement(data, "month").text = str(months[2][2])
            ET.SubElement(data, "year").text = str(years[2])
        if 'psh_2' in param_list:
            prc_list.append([idw_params[5], vector_classified[str(idw_params[5]).lower()]])
            date_list.append([months[2], years[2]])
            data = ET.SubElement(params, "data")
            ET.SubElement(data, "param").text = str(idw_params[0].split('_')[0])
            ET.SubElement(data, "month").text = str(months[2][2])
            ET.SubElement(data, "year").text = str(years[2])
        if 'pch_3' in param_list:
            prc_list.append([idw_params[6], vector_classified[str(idw_params[6]).lower()]])
            date_list.append([months[3], years[3]])
            data = ET.SubElement(params, "data")
            ET.SubElement(data, "param").text = str(idw_params[0].split('_')[0])
            ET.SubElement(data, "month").text = str(months[3][2])
            ET.SubElement(data, "year").text = str(years[3])
        if 'psh_3' in param_list:
            prc_list.append([idw_params[7], vector_classified[str(idw_params[7]).lower()]])
            date_list.append([months[3], years[3]])
            data = ET.SubElement(params, "data")
            ET.SubElement(data, "param").text = str(idw_params[0].split('_')[0])
            ET.SubElement(data, "month").text = str(months[3][2])
            ET.SubElement(data, "year").text = str(years[3])
        tree = ET.ElementTree(curah_hujan)
        tree.write(filename_xml, encoding='utf-8', xml_declaration=True)
        # Read Selected Region
        log.info('- Read Selected Region')
        output_log += '- Read Selected Region \n'
        query = (
            "UPDATE " + table_name +
            " SET output_log = %s "
            " WHERE id = %s "
        )
        data = (str(output_log), str(id_value))
        cur.execute(query, data)
        conn.commit()
        items = selected_region_format(selected_region)
        slc_id_list = [int(float(i[1])) for i in items]
        slc_name_list = [str(i[0]) for i in items]
        slc_nametitle_list = [str(i[2]) for i in items]
        # Polygon to Line Conversion
        log.info('- Polygon to Line Conversion')
        output_log += '- Polygon to Line Conversion \n'
        query = (
            "UPDATE " + table_name +
            " SET output_log = %s "
            " WHERE id = %s "
        )
        data = (str(output_log), str(id_value))
        cur.execute(query, data)
        conn.commit()
        provinsi_line = os.path.join(prcs_directory, 'provinsi_line.shp')
        if not os.path.exists(provinsi_line):
            log.info('-- Convert Province Boundary')
            output_log += '-- Convert Province Boundary \n'
            query = (
                "UPDATE " + table_name +
                " SET output_log = %s "
                " WHERE id = %s "
            )
            data = (str(output_log), str(id_value))
            cur.execute(query, data)
            conn.commit()
            general.runandload("qgis:polygonstolines", province_shp, provinsi_line)
            lineprovince = QgsMapLayerRegistry.instance().mapLayersByName('Lines from polygons')[0]
            QgsMapLayerRegistry.instance().removeMapLayer(lineprovince.id())
        kabupaten_line = os.path.join(prcs_directory, 'kabupaten_line.shp')
        if not os.path.exists(kabupaten_line):
            log.info('-- Convert Districts Boundary')
            output_log += '-- Convert Districts Boundary \n'
            query = (
                "UPDATE " + table_name +
                " SET output_log = %s "
                " WHERE id = %s "
            )
            data = (str(output_log), str(id_value))
            cur.execute(query, data)
            conn.commit()
            general.runandload("qgis:polygonstolines", districts_shp, kabupaten_line)
            linekabupaten = QgsMapLayerRegistry.instance().mapLayersByName('Lines from polygons')[0]
            QgsMapLayerRegistry.instance().removeMapLayer(linekabupaten.id())
        kecamatan_line = os.path.join(prcs_directory, 'kecamatan_line.shp')
        if not os.path.exists(kecamatan_line):
            log.info('-- Convert Sub-Districts Boundary')
            output_log += '-- Convert Sub-Districts Boundary \n'
            query = (
                "UPDATE " + table_name +
                " SET output_log = %s "
                " WHERE id = %s "
            )
            data = (str(output_log), str(id_value))
            cur.execute(query, data)
            conn.commit()
            general.runandload("qgis:polygonstolines", subdistricts_shp, kecamatan_line)
            linekecamatan = QgsMapLayerRegistry.instance().mapLayersByName('Lines from polygons')[0]
            QgsMapLayerRegistry.instance().removeMapLayer(linekecamatan.id())
        desa_line = os.path.join(prcs_directory, 'desa_line.shp')
        if not os.path.exists(desa_line):
            log.info('-- Convert Villages Boundary')
            output_log += '-- Convert Villages Boundary \n'
            query = (
                "UPDATE " + table_name +
                " SET output_log = %s "
                " WHERE id = %s "
            )
            data = (str(output_log), str(id_value))
            cur.execute(query, data)
            conn.commit()
            general.runandload("qgis:polygonstolines", village_shp, desa_line)
            linedesa = QgsMapLayerRegistry.instance().mapLayersByName('Lines from polygons')[0]
            QgsMapLayerRegistry.instance().removeMapLayer(linedesa.id())

        # Start Listing
        log.info('- Generate Map in Progress')
        output_log += '- Generate Map in Progress \n'
        query = (
            "UPDATE " + table_name +
            " SET output_log = %s "
            " WHERE id = %s "
        )
        data = (str(output_log), str(id_value))
        cur.execute(query, data)
        conn.commit()
        for value, date in zip(prc_list, date_list):
            log.info('-- Field (Parameter) : ' + value[0])
            output_log += '-- Field (Parameter) : ' + value[0] + ' \n'  
            query = (
                "UPDATE " + table_name +
                " SET output_log = %s "
                " WHERE id = %s "
            )
            data = (str(output_log), str(id_value))
            cur.execute(query, data)
            conn.commit()
            vector_classified = str(value[1])
            vector_classified_filename = os.path.basename(str(value[1]))
            style_file = os.path.join(classified_directory, os.path.splitext(vector_classified_filename)[0] + '.qml')
            temp_raster = os.path.join(prcs_directory, 'tmp' + str(vector_classified_filename))
            if not os.path.exists(temp_raster):
                os.mkdir(temp_raster)
            month = date[0]
            year = date[1]
            for slc_id, slc_name, slc_nametitle in zip(slc_id_list, slc_name_list, slc_nametitle_list):
                log.info('--- Region processed : ' + slc_name)
                output_log += '--- Region processed : ' + slc_name + ' \n'
                query = (
                    "UPDATE " + table_name +
                    " SET output_log = %s "
                    " WHERE id = %s "
                )
                data = (str(output_log), str(id_value))
                cur.execute(query, data)
                conn.commit()
                projectqgs = os.path.join(
                    prcs_directory,
                    '%s_qgisproject_%s_%s.qgs' % (
                        str(slc_name), str(value[0]), str(slc_id)
                    )
                )
                output_jpg = os.path.join(
                    map_directory,
                    '%s_%s%s_%s%s_%s_%s.jpg' % (
                        str(slc_id), str(years[4]), str(months[4]), str(year), str(month[2]), str(value[0]).split('_')[0], str(slc_name)
                    )
                )
                if os.path.basename(output_jpg) not in os.listdir(map_directory):
                    if len(str(slc_id)) == 2:
                        # Classified Value Styling
                        layer_vector = QgsVectorLayer(vector_classified, '', 'ogr')
                        layer_vector.loadNamedStyle(style_file)
                        # Province Styling
                        layer_provinsi = QgsVectorLayer(province_shp, 'Provinsi', 'ogr')
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
                        layer_kabupaten = QgsVectorLayer(districts_shp, 'Kabupaten', 'ogr')
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
                        layer_bath = QgsRasterLayer(bathymetry_raster, 'Bathymetry')
                        # Add Layer To QGIS Canvas
                        canvas = QgsMapCanvas()
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
                        template_file = open(map_template_1)
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
                        # Set Image
                        northarrow_item = composition.getComposerItemById('northarrow')
                        northarrow_item.setPictureFile(northarrow)
                        legenda_item = composition.getComposerItemById('legenda')
                        if str(value[0])[0:3].upper() == 'ACH' or str(value[0])[0:3].upper() == 'PCH':
                            legenda_item.setPictureFile(legenda_ch)
                        else:
                            legenda_item.setPictureFile(legenda_sh)
                        logo_item = composition.getComposerItemById('logo')
                        logo_item.setPictureFile(logo)
                        inset_item = composition.getComposerItemById('inset')
                        inset_item.setPictureFile(inset)
                        # Province Polygon As Extent
                        '''
                        if self.otoklimdlg.province_extent.isChecked():
                            map_item.zoomToExtent(canvas.extent())
                        '''
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
                    elif len(str(slc_id)) == 4:
                        # Classified Value Styling
                        layer_vector = QgsVectorLayer(vector_classified, '', 'ogr')
                        layer_vector.loadNamedStyle(style_file)
                        # Province Styling
                        layer_provinsi = QgsVectorLayer(province_shp, 'Provinsi', 'ogr')
                        symbol = QgsFillSymbolV2.createSimple({'color': '240,240,240,255', 'outline_color': '0,0,0,255', 'outline_style': 'solid', 'outline_width': '0.5'})
                        layer_provinsi.rendererV2().setSymbol(symbol)
                        layer_provinsi.triggerRepaint()
                        # Districts Styling
                        layer_kabupaten = QgsVectorLayer(districts_shp, 'Kabupaten', 'ogr')
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
                        layer_kecamatan = QgsVectorLayer(subdistricts_shp, 'Kecamatan', 'ogr')
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
                        layer_bath = QgsRasterLayer(bathymetry_raster, 'Bathymetry')
                        # Add Layer To QGIS Canvas
                        canvas = QgsMapCanvas()
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
                        template_file = open(map_template_2)
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
                        # Set Image
                        northarrow_item = composition.getComposerItemById('northarrow')
                        northarrow_item.setPictureFile(northarrow)
                        legenda_item = composition.getComposerItemById('legenda')
                        if str(value[0])[0:3].upper() == 'ACH' or str(value[0])[0:3].upper() == 'PCH':
                            legenda_item.setPictureFile(legenda_ch)
                        else:
                            legenda_item.setPictureFile(legenda_sh)
                        logo_item = composition.getComposerItemById('logo')
                        logo_item.setPictureFile(logo)
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
                        layer_provinsi = QgsVectorLayer(province_shp, 'Provinsi', 'ogr')
                        symbol = QgsFillSymbolV2.createSimple({'color': '240,240,240,255', 'outline_color': '0,0,0,255', 'outline_style': 'solid', 'outline_width': '0.5'})
                        layer_provinsi.rendererV2().setSymbol(symbol)
                        layer_provinsi.triggerRepaint()
                        # Districts Styling
                        layer_kabupaten = QgsVectorLayer(districts_shp, 'Kabupaten', 'ogr')
                        exp = "\"ID_PROV\"='{}' AND \"ID_KAB\"!='{}'".format(str(slc_id)[0:2], str(slc_id)[0:4])
                        layer_kabupaten.setSubsetString(exp)
                        symbol = QgsFillSymbolV2.createSimple({'color': '223,223,223,255', 'outline_color': '0,0,0,255', 'outline_style': 'solid', 'outline_width': '0.5'})
                        layer_kabupaten.rendererV2().setSymbol(symbol)
                        layer_kabupaten.triggerRepaint()
                        # Sub-Districts Styling
                        layer_kecamatan = QgsVectorLayer(subdistricts_shp, 'Kecamatan', 'ogr')
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
                        layer_desa = QgsVectorLayer(village_shp, 'Desa', 'ogr')
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
                        layer_bath = QgsRasterLayer(bathymetry_raster, 'Bathymetry')
                        # Add Layer To QGIS Canvas
                        canvas = QgsMapCanvas()
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
                        template_file = open(map_template_3)
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
                        # Set Image
                        northarrow_item = composition.getComposerItemById('northarrow')
                        northarrow_item.setPictureFile(northarrow)
                        legenda_item = composition.getComposerItemById('legenda')
                        if str(value[0])[0:3].upper() == 'ACH' or str(value[0])[0:3].upper() == 'PCH':
                            legenda_item.setPictureFile(legenda_ch)
                        else:
                            legenda_item.setPictureFile(legenda_sh)
                        logo_item = composition.getComposerItemById('logo')
                        logo_item.setPictureFile(logo)
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
        return output_log
    except Exception as errormessage:
        log.error(errormessage)
        output_log += errormessage + '\n'
        query = (
            "UPDATE " + table_name +
            " SET output_log = %s "
            " WHERE id = %s "
        )
        data = (str(output_log), str(id_value))
        cur.execute(query, data)
        conn.commit()
        return None


def generate_csv(
        output_log,
        table_name,
        cur,
        conn,
        id_value,
        project_parameter,
        classified,
        param_list,
        selected_region,
    ):
    """Genetare CSV"""
    try:
        log = project_parameter['log']
        log.info('Generate CSV')
        output_log += 'Generate CSV \n'
        query = (
            "UPDATE " + table_name +
            " SET output_log = %s "
            " WHERE id = %s "
        )
        data = (str(output_log), str(id_value))
        cur.execute(query, data)
        conn.commit()
        file_directory = project_parameter['project_directory']
        prcs_directory = project_parameter['processing_directory']
        out_directory = project_parameter['output_directory']
        csv_directory = project_parameter['csv_directory']
        classified_directory = project_parameter['classified_directory']
        # Spatial File
        districts_shp = project_parameter['shp_districts']
        subdistricts_shp = project_parameter['shp_subdistricts']
        village_shp = project_parameter['shp_villages']
        idw_params = classified[2]
        vector_classified = classified[1]
        raster_classified = classified[0]
        prc_list = []
        prc_list_fixed = []
        if 'ach_1' in param_list:
            prc_list.append([idw_params[0], vector_classified[str(idw_params[0]).lower()]])
            prc_list_fixed.append([idw_params[0], vector_classified[str(idw_params[0]).lower()]])
        else:
            prc_list_fixed.append(['', ''])
        if 'ash_1' in param_list:
            prc_list.append([idw_params[1], vector_classified[str(idw_params[1]).lower()]])
            prc_list_fixed.append([idw_params[1], vector_classified[str(idw_params[1]).lower()]])
        else:
            prc_list_fixed.append(['', ''])
        if 'pch_1' in param_list:
            prc_list.append([idw_params[2], vector_classified[str(idw_params[2]).lower()]])
            prc_list_fixed.append([idw_params[2], vector_classified[str(idw_params[2]).lower()]])
        else:
            prc_list_fixed.append(['', ''])
        if 'psh_1' in param_list:
            prc_list.append([idw_params[3], vector_classified[str(idw_params[3]).lower()]])
            prc_list_fixed.append([idw_params[3], vector_classified[str(idw_params[3]).lower()]])
        else:
            prc_list_fixed.append(['', ''])
        if 'pch_2' in param_list:
            prc_list.append([idw_params[4], vector_classified[str(idw_params[4]).lower()]])
            prc_list_fixed.append([idw_params[4], vector_classified[str(idw_params[4]).lower()]])
        else:
            prc_list_fixed.append(['', ''])
        if 'psh_2' in param_list:
            prc_list.append([idw_params[5], vector_classified[str(idw_params[5]).lower()]])
            prc_list_fixed.append([idw_params[5], vector_classified[str(idw_params[5]).lower()]])
        else:
            prc_list_fixed.append(['', ''])
        if 'pch_3' in param_list:
            prc_list.append([idw_params[6], vector_classified[str(idw_params[6]).lower()]])
            prc_list_fixed.append([idw_params[6], vector_classified[str(idw_params[6]).lower()]])
        else:
            prc_list_fixed.append(['', ''])
        if 'psh_3' in param_list:
            prc_list.append([idw_params[7], vector_classified[str(idw_params[7]).lower()]])
            prc_list_fixed.append([idw_params[7], vector_classified[str(idw_params[7]).lower()]])
        else:
            prc_list_fixed.append(['', ''])
        # Read Selected Region
        log.info('- Read Selected Region')
        output_log += '- Read Selected Region \n'
        query = (
            "UPDATE " + table_name +
            " SET output_log = %s "
            " WHERE id = %s "
        )
        data = (str(output_log), str(id_value))
        cur.execute(query, data)
        conn.commit()
        items = selected_region_format(selected_region)
        slc_id_list = [int(float(i[1])) for i in items]
        if len(prc_list) > 0:
            # Create CSV Default File
            log.info('- Create CSV Default File')
            output_log += '- Create CSV Default File \n'
            query = (
                "UPDATE " + table_name +
                " SET output_log = %s "
                " WHERE id = %s "
            )
            data = (str(output_log), str(id_value))
            cur.execute(query, data)
            conn.commit()
            driver = ogr.GetDriverByName("ESRI Shapefile")
            kabupaten_csv = os.path.join(csv_directory, 'kabupaten.csv')
            kecamatan_csv = os.path.join(csv_directory, 'kecamatan.csv')
            desa_csv = os.path.join(csv_directory, 'desa.csv')
            kabupaten_json = os.path.join(csv_directory, 'kabupaten.json')
            kecamatan_json = os.path.join(csv_directory, 'kecamatan.json')
            desa_json = os.path.join(csv_directory, 'desa.json')
            output_csv_list = [kabupaten_csv, kecamatan_csv, desa_csv]
            output_json_list = [kabupaten_json, kecamatan_json, desa_json]
            region_id_list = [1, 2, 3]
            shp_list = [
                districts_shp, 
                subdistricts_shp,
                village_shp
            ]
            json_kabupaten = []
            json_kecamatan = []
            json_desa = []

            csv_edit = []
            for i in slc_id_list:
                if len(str(i)) == 2:
                    csv_edit.append(1)
                elif len(str(i)) == 4:
                    csv_edit.append(2)
                else:
                    csv_edit.append(3)

            check_slc = []
            for shp, output_csv, output_json, region_id in zip(shp_list, output_csv_list, output_json_list, region_id_list):
                log.info('--- Generate in progress for :' + str(output_csv))
                output_log += '--- Generate in progress for :' + str(output_csv) + ' \n'
                query = (
                    "UPDATE " + table_name +
                    " SET output_log = %s "
                    " WHERE id = %s "
                )
                data = (str(output_log), str(id_value))
                cur.execute(query, data)
                conn.commit()
                n = 1
                if region_id in csv_edit:
                    with open(output_csv, "wb+") as csvfile:
                        if region_id == 1:
                            main_header = ['No', 'Provinsi', 'ID_Kabupaten_Kota', 'Kabupaten_Kota']
                        elif region_id == 2:
                            main_header = ['No', 'Provinsi', 'ID_Kabupaten_Kota', 'Kabupaten_Kota', 'ID_Kecamatan', 'Kecamatan']
                        else:
                            main_header = ['No', 'Provinsi', 'ID_Kabupaten_Kota', 'Kabupaten_Kota', 'ID_Kecamatan', 'Kecamatan', 'ID_Desa', 'Desa']
                        header = main_header
                        param = []
                        for prc in prc_list_fixed:
                            param_header = [prc[0].upper() + '_SBK', prc[0].upper() + '_SB', prc[0].upper() + '_SBB', prc[0].upper() + '_M']
                            param.append(param_header)
                            header += param_header
                        csv_writer = csv.DictWriter(csvfile, fieldnames=header,  delimiter=';')
                        csv_writer.writeheader()
                        for slc_id in slc_id_list:
                            if slc_id not in check_slc:
                                continue_run = True
                                if len(str(slc_id)) == 2 and region_id == 1:
                                    check_slc.append(slc_id)
                                    log.info('---- Region : ' + str(slc_id))
                                    output_log += '---- Region : ' + str(slc_id) + ' \n'
                                    query = (
                                        "UPDATE " + table_name +
                                        " SET output_log = %s "
                                        " WHERE id = %s "
                                    )
                                    data = (str(output_log), str(id_value))
                                    cur.execute(query, data)
                                    conn.commit()
                                    layer = QgsVectorLayer(shp, "PROVINSI", "ogr")
                                    exp = "\"ID_PROV\"='{}'".format(str(slc_id))
                                    layer.setSubsetString(exp)
                                elif len(str(slc_id)) == 4 and region_id == 2:
                                    check_slc.append(slc_id)
                                    log.info('---- Region : ' + str(slc_id))
                                    output_log += '---- Region : ' + str(slc_id) + ' \n'
                                    query = (
                                        "UPDATE " + table_name +
                                        " SET output_log = %s "
                                        " WHERE id = %s "
                                    )
                                    data = (str(output_log), str(id_value))
                                    cur.execute(query, data)
                                    conn.commit()
                                    layer = QgsVectorLayer(shp, "KABUPATEN", "ogr")
                                    exp = "\"ID_KAB\"='{}'".format(str(slc_id))
                                    layer.setSubsetString(exp)
                                elif len(str(slc_id)) == 7 and region_id == 3:
                                    check_slc.append(slc_id)
                                    log.info('---- Region : ' + str(slc_id))
                                    output_log += '---- Region : ' + str(slc_id) + ' \n'
                                    query = (
                                        "UPDATE " + table_name +
                                        " SET output_log = %s "
                                        " WHERE id = %s "
                                    )
                                    data = (str(output_log), str(id_value))
                                    cur.execute(query, data)
                                    conn.commit()
                                    layer = QgsVectorLayer(shp, "KECAMATAN", "ogr")
                                    exp = "\"ID_KEC\"='{}'".format(str(slc_id))
                                    layer.setSubsetString(exp)
                                else:
                                    continue_run = False
                                if continue_run:
                                    union_list = {}
                                    temp_list = []
                                    for prc in prc_list:
                                        log.info('----- Union :' + str(slc_id) + ' & ' + str(prc[0]))
                                        output_log += '----- Union :' + str(slc_id) + ' & ' + str(prc[0]) + ' \n'
                                        query = (
                                            "UPDATE " + table_name +
                                            " SET output_log = %s "
                                            " WHERE id = %s "
                                        )
                                        data = (str(output_log), str(id_value))
                                        cur.execute(query, data)
                                        conn.commit()
                                        vector_classified = os.path.join(classified_directory, prc[1])
                                        temp = os.path.join(prcs_directory, 'tmp_' + str(prc[0]))
                                        temp_list.append(temp)
                                        union = os.path.join(temp, str(slc_id) + '_' + str(prc[0]) + '_un.shp')
                                        if not os.path.exists(temp):
                                            os.mkdir(temp)
                                        general.runandload("qgis:union", vector_classified, layer, union)
                                        layer_union = QgsMapLayerRegistry.instance().mapLayersByName('Union')[0]
                                        QgsMapLayerRegistry.instance().removeMapLayer(layer_union)
                                        log.info('----- Union success.. Vector data has been stored on ' + str(union))
                                        output_log += '----- Union success.. Vector data has been stored on ' + str(union) + ' \n'
                                        query = (
                                            "UPDATE " + table_name +
                                            " SET output_log = %s "
                                            " WHERE id = %s "
                                        )
                                        data = (str(output_log), str(id_value))
                                        cur.execute(query, data)
                                        conn.commit()
                                        union_list.update({str(prc[0]):  str(union)})
                                    dataSource = driver.Open(shp, 0)
                                    layersource = dataSource.GetLayer()
                                    for feature in layersource:
                                        if (region_id == 1 and feature.GetField("ID_PROV") == slc_id) or (region_id == 2 and feature.GetField("ID_KAB") == slc_id) or (region_id == 3 and feature.GetField("ID_KEC") == slc_id):
                                            if region_id == 1:
                                                log.info('---- Region : ' + str(feature.GetField("ID_KAB")))
                                                output_log += '---- Region : ' + str(feature.GetField("ID_KAB")) + ' \n'
                                                query = (
                                                    "UPDATE " + table_name +
                                                    " SET output_log = %s "
                                                    " WHERE id = %s "
                                                )
                                                data = (str(output_log), str(id_value))
                                                cur.execute(query, data)
                                                conn.commit()
                                                main_values = {
                                                    'No': n,
                                                    'Provinsi': feature.GetField("PROVINSI"),
                                                    'ID_Kabupaten_Kota': feature.GetField("ID_KAB"),
                                                    'Kabupaten_Kota': feature.GetField("KABUPATEN")
                                                }
                                                exp = "\"ID_KAB\"='{}'".format(str(feature.GetField("ID_KAB")))
                                            elif region_id == 2:
                                                log.info('---- Region : ' + str(feature.GetField("ID_KEC")))
                                                output_log += '---- Region : ' + str(feature.GetField("ID_KEC")) + ' \n'
                                                query = (
                                                    "UPDATE " + table_name +
                                                    " SET output_log = %s "
                                                    " WHERE id = %s "
                                                )
                                                data = (str(output_log), str(id_value))
                                                cur.execute(query, data)
                                                conn.commit()
                                                main_values = {
                                                    'No': n,
                                                    'Provinsi': feature.GetField("PROVINSI"),
                                                    'ID_Kabupaten_Kota': feature.GetField("ID_KAB"),
                                                    'Kabupaten_Kota': feature.GetField("KABUPATEN"),
                                                    'ID_Kecamatan': feature.GetField("ID_KEC"),
                                                    'Kecamatan': feature.GetField("KECAMATAN")
                                                }
                                                exp = "\"ID_KEC\"='{}'".format(str(feature.GetField("ID_KEC")))
                                            else:
                                                log.info('---- Region : ' + str(feature.GetField("ID_DES")))
                                                output_log += '---- Region : ' + str(feature.GetField("ID_DES")) + ' \n'
                                                query = (
                                                    "UPDATE " + table_name +
                                                    " SET output_log = %s "
                                                    " WHERE id = %s "
                                                )
                                                data = (str(output_log), str(id_value))
                                                cur.execute(query, data)
                                                conn.commit()
                                                main_values = {
                                                    'No': n,
                                                    'Provinsi': feature.GetField("PROVINSI"),
                                                    'ID_Kabupaten_Kota': feature.GetField("ID_KAB"),
                                                    'Kabupaten_Kota': feature.GetField("KABUPATEN"),
                                                    'ID_Kecamatan': feature.GetField("ID_KEC"),
                                                    'Kecamatan': feature.GetField("KECAMATAN"),
                                                    'ID_Desa': feature.GetField("ID_DES"),
                                                    'Desa': feature.GetField("DESA")
                                                }
                                                exp = "\"ID_DES\"='{}'".format(str(feature.GetField("ID_DES")))
                                            param_values = {}
                                            for prc in prc_list:
                                                # Calculate Area
                                                log.info('----- Calculate Area Classified: ' + str(prc[0]))
                                                output_log += '----- Calculate Area Classified: ' + str(prc[0]) + ' \n'
                                                query = (
                                                    "UPDATE " + table_name +
                                                    " SET output_log = %s "
                                                    " WHERE id = %s "
                                                )
                                                data = (str(output_log), str(id_value))
                                                cur.execute(query, data)
                                                conn.commit()
                                                sbk = {}
                                                sb = {}
                                                sbb = {}
                                                m = {}
                                                unique_counts = {}
                                                expression = QgsExpression("area(transform($geometry, 'EPSG:4326','EPSG:3857'))")
                                                layer_union = QgsVectorLayer(union_list[str(prc[0])], str(prc[0]), 'ogr')
                                                layer_union.setSubsetString(exp)
                                                index = layer_union.fieldNameIndex("Area")
                                                expression.prepare(layer_union.pendingFields())
                                                area_all = 0
                                                features = layer_union.getFeatures()
                                                for i in features:
                                                    if i[prc[0].upper().split('_')[0]]:
                                                        if expression.evaluate(i):
                                                            area_all += expression.evaluate(i)
                                                        else:
                                                            area_all += 0
                                                layer_union.startEditing()
                                                features = layer_union.getFeatures()
                                                for i in features:
                                                    if i[prc[0].upper().split('_')[0]]:
                                                        if expression.evaluate(i):
                                                            area = expression.evaluate(i)
                                                        else:
                                                            area = 0
                                                        layer_union.changeAttributeValue(
                                                            i.id(),
                                                            layer_union.fieldNameIndex('Area'), 
                                                            area
                                                        )
                                                        layer_union.changeAttributeValue(
                                                            i.id(),
                                                            layer_union.fieldNameIndex('Percent'), 
                                                            (area / float(area_all)) * 100
                                                        )
                                                        if i[prc[0].upper().split('_')[0]] not in unique_counts:
                                                            unique_counts[i[prc[0].upper().split('_')[0]]] = (area / float(area_all)) * 100
                                                        else:
                                                            unique_counts[i[prc[0].upper().split('_')[0]]] += (area / float(area_all)) * 100
                                                layer_union.commitChanges()
                                                for key, value in zip(unique_counts.keys(), unique_counts.values()):
                                                    if value > 0 and value < 20:
                                                        sbk.update({key: value})
                                                    elif value >= 20 and value < 50:
                                                        sb.update({key: value})
                                                    elif value >= 50 and value < 100:
                                                        sbb.update({key: value})
                                                    elif value == 100:
                                                        m.update({key: value})
                                                param_values.update({
                                                    prc[0].upper() + '_SBK': sbk,
                                                    prc[0].upper() + '_SB': sb,
                                                    prc[0].upper() + '_SBB': sbb,
                                                    prc[0].upper() + '_M': m
                                                })
                                            # JSON Structure
                                            log.info('----- Write JSON')
                                            output_log += '----- Write JSON \n'
                                            query = (
                                                "UPDATE " + table_name +
                                                " SET output_log = %s "
                                                " WHERE id = %s "
                                            )
                                            data = (str(output_log), str(id_value))
                                            cur.execute(query, data)
                                            conn.commit()
                                            json_values = {}
                                            json_values.update({"VALUES": param_values})
                                            json_values.update(main_values)
                                            if region_id == 1:
                                                json_kabupaten.append(json_values)
                                            elif region_id == 2:
                                                json_kecamatan.append(json_values)
                                            else:
                                                json_desa.append(json_values)
                                            # CSV Structure
                                            main_values.update(param_values)
                                            log.info('----- Write CSV')
                                            output_log += '----- Write CSV \n'
                                            query = (
                                                "UPDATE " + table_name +
                                                " SET output_log = %s "
                                                " WHERE id = %s "
                                            )
                                            data = (str(output_log), str(id_value))
                                            cur.execute(query, data)
                                            conn.commit()
                                            csv_writer.writerow(main_values)
                                            n += 1
                                    del layer_union    
                                    dataSource.Destroy()
                                    for temp in temp_list:
                                        shutil.rmtree(temp)
                    with open(output_json, 'w') as jsonfile:
                        if region_id == 1:
                            jsonfile.write(json.dumps(json_kabupaten, indent=4))
                        elif region_id == 2:
                            jsonfile.write(json.dumps(json_kecamatan, indent=4))
                        else:
                            jsonfile.write(json.dumps(json_desa, indent=4))
    except Exception as errormessage:
        log.info(errormessage)
        output_log += errormessage + '\n'
        query = (
            "UPDATE " + table_name +
            " SET output_log = %s "
            " WHERE id = %s "
        )
        data = (str(output_log), str(id_value))
        cur.execute(query, data)
        conn.commit()
        return None


if __name__ == '__main__':
    try:
        # Start Time
        start_time = '{:%Y-%m-%d %H:%M:%S}'.format(datetime.datetime.now())
        # Initialize the parser
        parser = argparse.ArgumentParser(
            description="Parsing Otoklim Parameter"
        )

        # Files Storage Path & Folder
        currentpath = os.path.dirname(os.path.abspath(__file__))
        filepath = 'sample_files'
        projectpath = os.path.join('uploaded', 'dirproject')

        # Add parameter
        # Databases Parameter
        parser.add_argument('--id_value', help="PK Value", type=str, nargs='?', const="0")
        parser.add_argument('--dbname', help="Name of databases", type=str)
        parser.add_argument('--user', help="Databases user", type=str)
        parser.add_argument('--host', help="Host", type=str)
        parser.add_argument('--password', help="Password", type=str)

        # Otoklim Site
        parser.add_argument('--otoklim_site', help="Otoklim Site", type=str, nargs='?', const="url")

        # Geoserver Parameter
        parser.add_argument('--gs_url', help="Geo Server URL", type=str)
        parser.add_argument('--gs_username', help="Geo Server Username")
        parser.add_argument('--gs_password', help="Geo Server Password")

        # Project Parameter
        parser.add_argument('--project_name', help="Project Name", type=str, nargs='?', const="project1")
        parser.add_argument('--csv_delimiter', help="CSV Input Delimiter", type=str, nargs='?', const=",")
        parser.add_argument(
            '--province_shp',
            help="Shapefile for Province Administration Boundary in Indonesia",
            type=str, nargs='?',
            const=os.path.join(currentpath, filepath, 'Admin_Provinsi_BPS2013_GEO.zip')
        )
        parser.add_argument(
            '--districts_shp',
            help="Shapefile for Districts Administration Boundary in Indonesia",
            type=str, nargs='?',
            const=os.path.join(currentpath, filepath, 'Admin_Kabupaten_BPS2013_GEO.zip')
        )
        parser.add_argument(
            '--subdistricts_shp',
            help="Shapefile for Sub-districts Administration Boundary in Indonesia",
            type=str, nargs='?',
            const=os.path.join(currentpath, filepath, 'Admin_Kecamatan_BPS2013_GEO.zip')
        )
        parser.add_argument(
            '--village_shp',
            help="Shapefile for Villages Administration Boundary in Indonesia",
            type=str, nargs='?',
            const=os.path.join(currentpath, filepath, 'Admin_Desa_BPS2013_GEO.zip')
        )
        parser.add_argument(
            '--bathymetry_raster',
            help="Bathymetry file for Indonesia ocean in raster",
            type=str, nargs='?',
            const=os.path.join(currentpath, filepath, 'byth_gebco_invert.tif')
        )
        parser.add_argument(
            '--rainpost_file',
            help="BMKG Rainpost data in CSV format including Location in Lat\lon",
            type=str, nargs='?',
            const=os.path.join(currentpath, filepath, 'rainpost_jatim.csv')
        )
        parser.add_argument(
            '--rainfall_class',
            help="Classification rule for rainfall such as domain, range, and color in CSV",
            type=str, nargs='?',
            const=os.path.join(currentpath, filepath, 'rule_ch.csv')
        )
        parser.add_argument(
            '--normalrain_class',
            help="Classification rule for normal rain such as domain, range, and color in CSV",
            type=str, nargs='?',
            const=os.path.join(currentpath, filepath, 'rule_sh.csv')
        )
        parser.add_argument(
            '--map_template_1',
            help="QGIS Template (QPT) file that will be used for province map",
            type=str, nargs='?',
            const=os.path.join(currentpath, filepath, 'template', 'jatim_ch.qpt')
        )
        parser.add_argument(
            '--map_template_2',
            help="QGIS Template (QPT) file that will be used for districts map",
            type=str, nargs='?',
            const=os.path.join(currentpath, filepath, 'template', 'jatim_umum_ch.qpt')
        )
        parser.add_argument(
            '--map_template_3',
            help="QGIS Template (QPT) file that will be used for sub-districts map",
            type=str, nargs='?',
            const=os.path.join(currentpath, filepath, 'template', 'jatim_umum_ch.qpt')
        )

        # Param To Be Processed
        parser.add_argument(
            '--param_list',
            help="List of Param to be processed",
            type=str, nargs='?',
            #const=['ach_1', 'ash_1', 'pch_1', 'psh_1', 'pch_2', 'psh_2', 'pch_3', 'psh_3']
            const=['ach_1']
        )

        # Interpolation Parameter and Classification Parameter
        parser.add_argument(
            '--input_value_csv',
            help="Values for every rainpost data in CSV",
            type=str, nargs='?',
            const=os.path.join(currentpath, filepath, 'input_sample_jatim.csv')
        )
        parser.add_argument('--province', help="Province Name", type=str, nargs='?', const="Jawa Timur")
        parser.add_argument('--month', help="Current Month", type=int, nargs='?', const=datetime.datetime.now().month)
        parser.add_argument('--year', help="Current Year", type=int, nargs='?', const=datetime.datetime.now().year)
        parser.add_argument('--number_of_interpolation', help="Number of Interpolation for IDW", type=float, nargs='?', const=8.0)
        parser.add_argument('--power_parameter', help="Power parameter for IDW", type=float, nargs='?', const=5.0)
        parser.add_argument('--cell_size', help="Output raster interpolated cell size in degrees", type=float, nargs='?', const=0.001)

        # Generate MAP and CSV Parameter
        parser.add_argument(
            '--selected_region',
            help="List of Region to be processed",
            type=str, nargs='?',
            #const=[['JAWA TIMUR', 'PROVINSI', 35],['BANYUWANGI', 'KABUPATEN', 3510, 'JAWA TIMUR'],['TEGALDLIMO', 'KECAMATAN', 3510040, 'BANYUWANGI', 'JAWA TIMUR']]
            const=[['JAWA TIMUR', 'PROVINSI', 35]]
        )
        parser.add_argument('--date_produced', help="Date when map is produced", type=str, nargs='?', const="??")
        parser.add_argument(
            '--northarrow',
            help="Northarrow icon for map",
            type=str, nargs='?',
            const=os.path.join(currentpath, filepath, 'northarrow.PNG')
        )
        parser.add_argument(
            '--logo',
            help="Logo image for map",
            type=str, nargs='?',
            const=os.path.join(currentpath, filepath, 'logo_jatim.png')
        )
        parser.add_argument(
            '--inset',
            help="Inser for province map",
            type=str, nargs='?',
            const=os.path.join(currentpath, filepath, 'jatim_inset.png')
        )
        parser.add_argument(
            '--legenda_ch',
            help="Map Legend for rainfall",
            type=str, nargs='?',
            const=os.path.join(currentpath, filepath, 'legenda_ch_landscape.PNG')
        )
        parser.add_argument(
            '--legenda_sh',
            help="Map Legend for normalrain",
            type=str, nargs='?',
            const=os.path.join(currentpath, filepath, 'legenda_sh_landscape.PNG')
        )

        # Parse the arguments
        arguments = parser.parse_args()

        # Set Databases Parameter
        id_value = arguments.id_value
        dbname = arguments.dbname
        user = arguments.user
        host = arguments.host
        password = arguments.password
        conn = psycopg2.connect("dbname=%s user=%s host=%s password=%s" % (dbname, user, host, password))
        cur = conn.cursor()
        table_name = "otoklim_otoklimjob"
        # Start Update DB
        create_time = '{:%Y-%m-%d %H:%M:%S}'.format(datetime.datetime.now())
        query = (
            "UPDATE " + table_name +
            " SET started_at = %s, "
            " created_at = %s, "
            " status = %s "
            " WHERE id = %s "
        )
        data = (start_time, create_time, 'started', str(id_value))
        cur.execute(query, data)
        conn.commit()

        # Geoserver Parameter
        gs_url = arguments.gs_url
        gs_username = arguments.gs_username
        gs_password = arguments.gs_password
    
        # Project Parameter
        project_name = arguments.project_name
        project_name = project_name.strip()
        project_name = project_name.replace(" ", "_")
        # Clean project name
        otoklim_site = arguments.otoklim_site
        project_fullpath = os.path.join(otoklim_site, 'projects', project_name + '/')
        query = (
            "UPDATE " + table_name +
            " SET project_url = %s "
            " WHERE id = %s "
        )
        data = (str(project_fullpath), str(id_value))
        cur.execute(query, data)
        conn.commit()
        project_workspace = os.path.join(currentpath, projectpath, project_name)
        csv_delimiter = arguments.csv_delimiter
        province_shp = arguments.province_shp
        districts_shp = arguments.districts_shp
        subdistricts_shp = arguments.subdistricts_shp
        village_shp = arguments.village_shp
        bathymetry_raster = arguments.bathymetry_raster
        rainpost_file = arguments.rainpost_file
        rainfall_class = arguments.rainfall_class
        normalrain_class = arguments.normalrain_class
        map_template_1 = arguments.map_template_1
        map_template_2 = arguments.map_template_2
        map_template_3 = arguments.map_template_3
        # Param To Be Processed
        param_list = arguments.param_list
        # Interpolation and Classification Parameter
        input_value_csv = arguments.input_value_csv
        province = arguments.province
        month = arguments.month
        year = arguments.year
        number_of_interpolation = arguments.number_of_interpolation
        power_parameter = arguments.power_parameter
        cell_size = arguments.cell_size
        # Generate MAP and CSV Parameter
        selected_region = arguments.selected_region
        date_produced = arguments.date_produced
        northarrow = arguments.northarrow
        logo = arguments.logo
        inset = arguments.inset
        legenda_ch = arguments.legenda_ch
        legenda_sh = arguments.legenda_sh

        # Run Otoklim
        finish = False
        output_log = ""
        project_parameter = create_project(
            table_name,
            cur,
            conn,
            id_value,
            project_name,
            project_workspace,
            csv_delimiter,
            province_shp,
            districts_shp,
            subdistricts_shp,
            village_shp,
            bathymetry_raster,
            rainpost_file,
            rainfall_class,
            normalrain_class,
            map_template_1,
            map_template_2,
            map_template_3
        )
        if project_parameter:
            interpolated = interpolate_idw(
                table_name,
                cur,
                conn,
                id_value,
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
                table_name,
                cur,
                conn,
                id_value,
                project_parameter,
                interpolated,
                rainfall_class,
                normalrain_class,
                csv_delimiter,
                param_list
            )
        else:
            classified = None

        if classified and project_parameter:
            output_log_1 = push_to_geoserver(
                gs_url,
                gs_username,
                gs_password,
                project_name,
                otoklim_site,
                project_parameter,
                classified
            )

        if classified and project_parameter:
            output_log_2 = generate_map(
                output_log_1,
                table_name,
                cur,
                conn,
                id_value,
                project_parameter,
                classified,
                month,
                year,
                param_list,
                selected_region,
                map_template_1,
                map_template_2,
                map_template_3,
                date_produced,
                northarrow,
                legenda_ch,
                legenda_sh,
                logo,
                inset
            )

        if classified and project_parameter:
            generate_csv(
                output_log_2,
                table_name,
                cur,
                conn,
                id_value,
                project_parameter,
                classified,
                param_list,
                selected_region,
            )
            finish = True

        # Otoklim Finished \ Failed
        end_time = '{:%Y-%m-%d %H:%M:%S}'.format(datetime.datetime.now())
        query = (
            "UPDATE " + table_name +
            " SET ended_at = %s, "
            " status = %s"
            " WHERE id = %s "
        )
        if finish:
            data = (end_time, 'finished', str(id_value))
        else:
            data = (end_time, 'failed', str(id_value))
        cur.execute(query, data)
        conn.commit()
        # DB Close
        cur.close()
        conn.close()
    except Exception as err:
        print str(err)

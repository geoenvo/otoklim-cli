import os 
import sys
from qgis.core import *
from qgis.gui import QgsMapCanvas, QgsLayerTreeMapCanvasBridge
import qgis.utils

from PyQt4.QtCore import *
from PyQt4.QtXml import QDomDocument
from PyQt4.QtGui import *


# subprocess.call(['sudo', 'python', 'run_otoklim.py']) 
qgisprefix = '/usr'
currentpath = os.path.dirname(os.path.abspath(__file__))
filepath = 'sample_files'
#qgisprefix='/usr/share/qgis/resources' 

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


def interpolate():
    from processing.core.Processing import Processing

    Processing.initialize()

    from processing.tools import general

    provinsi_polygon_file = os.path.join(currentpath, filepath, 'provinsi_polygon.shp')
    layer_provinsi = QgsVectorLayer(provinsi_polygon_file, 'layer', 'ogr')
    extent = layer_provinsi.extent()

    filename_shp_tmp = os.path.join(currentpath, filepath, 'rainpost_point_ACH_NOV.shp')
    layer = QgsVectorLayer(filename_shp_tmp, 'layer', 'ogr')


    raster_interpolated = os.path.join(currentpath, filepath, 'interpolated_uncliped.tif')
    general.runalg(
        'grass7:v.surf.idw',
        layer, 8.0, 5.0, 'ACH_NOV', False,
        "%f,%f,%f,%f" % (extent.xMinimum(), extent.xMaximum(), extent.yMinimum(), extent.yMaximum()), 0.001, -1.0, 0.0001,
        raster_interpolated
    )

    raster_cliped = os.path.join(currentpath, filepath, 'interpolated_cliped.tif')
    raster_layer = QgsRasterLayer(raster_interpolated, 'raster')
    mask_layer = QgsVectorLayer(provinsi_polygon_file, 'mask', 'ogr')
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


if __name__ == '__main__':
    #interpolate()
    classify()
    #generate_map()
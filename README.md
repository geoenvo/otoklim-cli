# Guide
### Installation
Source : https://www.qgis.org/en/site/forusers/alldownloads.html
Adding QGIS Repo:
```
echo 'deb     https://qgis.org/debian-ltr xenial main' >> /etc/apt/sources.list
echo 'deb-src https://qgis.org/debian-ltr xenial main' >> /etc/apt/sources.list
sudo apt-key adv --keyserver keyserver.ubuntu.com --recv-key CAEB3DC3BDF7FB45
```

Install Python, PyPi and QGIS:
```
sudo apt-get install -y python python-dev python-pip
sudo apt-get install -y qgis python-qgis qgis-plugin-grass
```

Install Xvfb and pyvirtualdisplay:
```
sudo apt-get install xvfb xserver-xephyr vnc4server
sudo pip install pyvirtualdisplay
```

Clone otoklim-cli from repo:
```
git clone https://github.com/geoenvo/otoklim-cli.git
```
Download and copy Sample File into "sample_files" folder
https://drive.google.com/drive/folders/1zldrAgEvGpsxuvOhitDP4y6FoUwm0Kr_
### How to Run Otoklim
```
cd otoklim-cli
```
This is how to run Otoklim by using default value:
```
sudo python run_otoklim.py --project_name  --csv_delimiter --province_shp --districts_shp --subdistricts_shp --village_shp --bathymetry_raster --rainpost_file --rainfall_class --normalrain_class --map_template_1 --map_template_2 --map_template_3 --param_list --input_value_csv --province --month --year --number_of_interpolation --power_parameter --cell_size --selected_region --date_produced --northarrow --logo --inset --legenda_ch --legenda_sh
```
To set values, add those after specific parameter:
```
sudo python run_otoklim.py --project_name  [value] --csv_delimiter [value] --province_shp [value] --districts_shp [value] --subdistricts_shp [value] --village_shp [value] --bathymetry_raster [value] --rainpost_file [value] --rainfall_class [value] --normalrain_class [value] --map_template_1 [value] --map_template_2 [value] --map_template_3 [value] --param_list [value] --input_value_csv [value] --province [value] --month [value] --year [value] --number_of_interpolation [value] --power_parameter [value] --cell_size [value] --selected_region [value] --date_produced [value] --northarrow [value] --logo --inset [value] --legenda_ch [value] --legenda_sh [value]
```
### Parameter Guide
--project_name :
  - Type : string
  - Default :  'project1'
  - Project name used as workspace folder name

--csv_delimiter:
  - Type : string
  - Default :  ','
  - Delimiter used to separate values of CSV input file

--province_shp:
  - Type : string
  - File Type : Shapefiles
  - Default :  'path_to_otoklim_file/sample_files/Admin_Provinsi_BPS2013_GEO.shp'
  - Shapefile for Province Administration Boundary in Indonesia

--districts_shp:
  - Type : string
  - File Type : Shapefiles
  - Default :  'path_to_otoklim_file/sample_files/Admin_Kabupaten_BPS2013_GEO.shp'
  - Shapefile for Districts Administration Boundary in Indonesia

--subdistricts_shp:
  - Type : string
  - File Type : Shapefiles
  - Default :  'path_to_otoklim_file/sample_files/Admin_Kecamatan_BPS2013_GEO.shp'
  - Shapefile for Sub-districts Administration Boundary in Indonesia

--village_shp:
  - Type : string
  - File Type : Shapefiles
  - Default :  'path_to_otoklim_file/sample_files/Admin_Desa_BPS2013_GEO.shp'
  - Shapefile for Villages Administration Boundary in Indonesia

--bathymetry_raster:
  - Type : string
  - File Type : OGC Raster format (GeoTIF, ASC, HGT, JPEG, etc)
  - Default :  'path_to_otoklim_file/sample_files/byth_gebco_invert.tif'
  - Bathymetry file for Indonesia ocean in raster format

--rainpost_file:
  - Type : string
  - File Type : CSV
  - Default :  'path_to_otoklim_file/sample_files/rainpost_jatim.csv'
  - BMKG Rainpost data in CSV format including Location in Lat\lon

--rainfall_class:
  - Type : string
  - File Type : CSV
  - Default :  'path_to_otoklim_file/sample_files/rule_ch.csv'
  - Classification rule for rainfall such as domain, range, and color in CSV

--normalrain_class:
  - Type : string
  - File Type : CSV
  - Default :  'path_to_otoklim_file/sample_files/rule_sh.csv'
  - Classification rule for normal rain such as domain, range, and color in CSV

--map_template_1:
  - Type : string
  - File Type : QPT
  - Default :  'path_to_otoklim_file/sample_files/template/jatim_ch.qpt'
  - QGIS Template (QPT) file that will be used for province map

--map_template_2:
  - Type : string
  - File Type : QPT
  - Default :  'path_to_otoklim_file/sample_files/template/jatim_umum_ch.qpt'
  - QGIS Template (QPT) file that will be used for districts map

--map_template_3:
  - Type : string
  - File Type : QPT
  - Default :  'path_to_otoklim_file/sample_files/template/jatim_umum_ch.qpt'
  - QGIS Template (QPT) file that will be used for sub-districts map

--param_list:
  - Type : string \ list
  - Default :  '['ach_1', 'ash_1', 'pch_1', 'psh_1', 'pch_2', 'psh_2', 'pch_3', 'psh_3']'
  - List of Parameter to be processed

--input_value_csv:
  - Type : string
  - File Type : CSV
  - Default :  'path_to_otoklim_file/sample_files/input_sample_jatim.csv'
  - Values for every rainpost data in CSV

--province:
  - Type : string
  - Default :  'Jawa Timur'
  - Province Name

--month:
  - Type : integer
  - Default :  Current month
  - Month when analysis performed

--year:
  - Type : integer
  - Default :  Current Year
  - Year when analysis performed

--number_of_interpolation:
  - Type : float
  - Default :  8.0
  - Number of Interpolation Point for IDW (https://gisgeography.com/inverse-distance-weighting-idw-interpolation/)

--power_parameter:
  - Type : float
  - Default :  5.0
  - Power parameter for IDW (https://gisgeography.com/inverse-distance-weighting-idw-interpolation/)

--cell_size:
  - Type : float
  - Default :  0.001
  - Output raster interpolated cell size in degrees (1 degrees WGS'84 ~ 111,139 meters)

--selected_region:
  - Type : string / list
  - Default : 
  ```
  [['JAWA TIMUR', 'PROVINSI', 35], ['BANYUWANGI', 'KABUPATEN', 3510, 'JAWA TIMUR'], ['TEGALDLIMO', 'KECAMATAN', 3510040, 'BANYUWANGI', 'JAWA TIMUR']]
  ```
  - List of Region to be processed (including name, title, and BPS code)

--date_produced:
  - Type : string
  - Default :  ??
  - Date or statement when map is produced

--northarrow:
  - Type : string
  - File Type : PNG \ JPEG
  - Default :  path_to_otoklim_file/sample_files/northarrow.PNG'
  - Northarrow icon for map
 
--logo:
  - Type : string
  - File Type : PNG \ JPEG
  - Default :  path_to_otoklim_file/sample_files/logo_jatim.PNG'
  - Logo image for map
 
--inset:
  - Type : string
  - File Type : PNG \ JPEG
  - Default :  path_to_otoklim_file/sample_files/jatim_inset.png'
  - Inser for province map
 
--legenda_ch:
  - Type : string
  - File Type : PNG \ JPEG
  - Default :  path_to_otoklim_file/sample_files/legenda_ch_landscape.PNG'
  - Map Legend for rainfall
 
--legenda_Sh:
  - Type : string
  - File Type : PNG \ JPEG
  - Default :  path_to_otoklim_file/sample_files/legenda_sh_landscape.PNG'
  - Map Legend for normalrain
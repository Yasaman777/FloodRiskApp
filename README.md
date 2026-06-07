Link App: floodriskapp-production.up.railway.app 
# 🌊 Flood Risk Mapping WebGIS

## Overview

Flood Risk Mapping WebGIS is a Python-based application developed to identify flood-prone areas at the district (kecamatan) level using topographic, hydrological, and land cover data.

The application integrates DEM processing, hydrological analysis, Topographic Wetness Index (TWI), ESA WorldCover land cover classification, and Weighted Overlay Analysis to generate Flood Risk Maps automatically through a Streamlit web interface.

---

## Objectives

The objectives of this project are:

* Identify flood risk levels at the district scale.
* Automate GIS-based flood risk analysis.
* Develop an interactive WebGIS application using Python and Streamlit.
* Support flood mitigation and spatial planning activities.

---

## Study Area

This project was initially developed and tested using Kecamatan Cisarua, West Java, Indonesia.

---

## Data Sources

### 1. DEM (Digital Elevation Model)

Used to generate:

* Elevation
* Slope
* Flow Direction
* Flow Accumulation
* Stream Network
* Distance to Stream
* Topographic Wetness Index (TWI)

### 2. ESA WorldCover

Used for land cover classification.

Classes include:

* Tree Cover
* Shrubland
* Grassland
* Cropland
* Built-up Area
* Wetland
* Water Bodies

### 3. Administrative Boundary

District boundary shapefile used for clipping and area selection.

---

## Methodology

### Workflow

DEM
↓
DEM Conditioning
↓
Flow Direction
↓
Flow Accumulation
↓
Stream Network Extraction
↓
Distance to Stream
↓
Slope Analysis
↓
Topographic Wetness Index
↓
Land Cover Classification
↓
Weighted Overlay Analysis
↓
Flood Risk Map

---

## Flood Risk Parameters

| Parameter          | Weight |
| ------------------ | ------ |
| Flow Accumulation  | 20%    |
| Distance to Stream | 25%    |
| Slope              | 10%    |
| Elevation          | 10%    |
| ESA Land Cover     | 15%    |
| TWI                | 20%    |

---

## Technologies Used

* Python 3.11
* Streamlit
* Rasterio
* GeoPandas
* NumPy
* SciPy
* Matplotlib
* Pysheds

---

## Features

* Automatic DEM clipping
* Hydrological analysis
* Stream network extraction
* Distance to stream calculation
* TWI generation
* Flood risk classification
* GeoTIFF export
* PNG export
* Interactive WebGIS interface

---

## Outputs

The application generates:

* Flood Risk Map
* DEM Visualization
* Slope Map
* Flow Accumulation Map
* Stream Network Map
* Distance to Stream Map
* TWI Map
* ESA WorldCover Map

---

## Results Example

Flood risk is classified into:

* Low Risk
* Medium Risk
* High Risk

The output can be downloaded as GeoTIFF and PNG files.

---

## Future Improvements

* Rainfall integration
* Real river network integration
* Multi-temporal flood analysis
* Machine Learning-based flood susceptibility modeling
* Web deployment using Streamlit Cloud

---

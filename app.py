import streamlit as st
import geopandas as gpd
import rasterio
import rasterio.mask
import numpy as np
import matplotlib.pyplot as plt
import os
import zipfile
import requests

# =========================================
# PAGE CONFIG
# =========================================

st.set_page_config(
    page_title="Flood Risk Mapping App",
    page_icon="🌊",
    layout="wide"
)

# =========================================
# CUSTOM CSS
# =========================================

st.markdown("""
<style>

.main {
    background-color: #f5f7fa;
}

.block-container {
    padding-top: 2rem;
}

h1, h2, h3 {
    color: #0f172a;
}

.sidebar .sidebar-content {
    background-color: #0f172a;
}

</style>
""", unsafe_allow_html=True)

# =========================================
# GOOGLE DRIVE FILE IDS
# =========================================

DEM_ID = "1Y23GSWnk8Rss0iFTc8ZwxN84j4dvfy4d"
SHP_ID = "1EiZSbdr31IDsANsu8_mpjrRwdBWHIy8c"

# =========================================
# FOLDER SETUP
# =========================================

os.makedirs("data", exist_ok=True)

dem_path = "data/dem_jabar.tif"
zip_path = "data/batas_kecamatan.zip"
extract_path = "data/shapefile"

# =========================================
# DOWNLOAD DEM
# =========================================

if not os.path.exists(dem_path):

    st.info("Downloading DEM Jawa Barat...")

    url = f"https://drive.google.com/uc?export=download&id={DEM_ID}"

    response = requests.get(url)

    with open(dem_path, "wb") as f:
        f.write(response.content)

# =========================================
# DOWNLOAD SHAPEFILE ZIP
# =========================================

if not os.path.exists(zip_path):

    st.info("Downloading batas kecamatan...")

    url = f"https://drive.google.com/uc?export=download&id={SHP_ID}"

    response = requests.get(url)

    with open(zip_path, "wb") as f:
        f.write(response.content)

# =========================================
# EXTRACT ZIP
# =========================================

if not os.path.exists(extract_path):

    os.makedirs(extract_path, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(extract_path)

# =========================================
# CARI FILE SHP
# =========================================

shp_file = None

for root, dirs, files in os.walk(extract_path):

    for file in files:

        if file.lower().endswith(".shp"):

            shp_file = os.path.join(root, file)

# =========================================
# VALIDASI SHP
# =========================================

if shp_file is None:

    st.error("File shapefile (.shp) tidak ditemukan.")
    st.stop()

# =========================================
# LOAD SHAPEFILE
# =========================================

batas = gpd.read_file(shp_file)

# =========================================
# BERSIHKAN DATA
# =========================================

batas = batas.dropna(subset=["WADMKC"])

# =========================================
# SIDEBAR
# =========================================

st.sidebar.title("🌊 Parameter Analysis")

st.sidebar.write(
    "Pilih wilayah yang ingin dianalisis."
)

# =========================================
# LIST KECAMATAN
# =========================================

daftar_kecamatan = sorted(
    batas["WADMKC"].astype(str).unique()
)

kecamatan_pilih = st.sidebar.selectbox(
    "Pilih Kecamatan",
    daftar_kecamatan
)

# =========================================
# FILTER WILAYAH
# =========================================

wilayah = batas[
    batas["WADMKC"] == kecamatan_pilih
]

# =========================================
# KABUPATEN
# =========================================

kabupaten = wilayah.iloc[0]["WADMKK"]

st.sidebar.selectbox(
    "Pilih Kabupaten/Kota",
    [kabupaten]
)

# =========================================
# PARAMETER
# =========================================

st.sidebar.markdown("---")

st.sidebar.write("Bobot analisis:")

st.sidebar.write("Flow Accumulation: 50%")
st.sidebar.write("Slope: 25%")
st.sidebar.write("Elevation: 25%")

# =========================================
# HEADER
# =========================================

st.title("🌊 Flood Risk Mapping App")

st.write(
    "Aplikasi WebGIS Analisis Kerawanan Banjir"
)

st.info("""
Metode:
Aplikasi ini melakukan clipping DEM berdasarkan batas kecamatan,
kemudian menghitung slope dan elevasi untuk menghasilkan
peta flood risk.
""")

# =========================================
# BUTTON
# =========================================

if st.button("🚀 Proses Flood Risk Map"):

    st.success(
        f"Wilayah ditemukan: {kecamatan_pilih}, {kabupaten}"
    )

    # =====================================
    # CLIP DEM
    # =====================================

    with rasterio.open(dem_path) as src:

        geoms = wilayah.geometry.values

        out_image, out_transform = rasterio.mask.mask(
            src,
            geoms,
            crop=True
        )

    dem = out_image[0]

    # =====================================
    # NODATA
    # =====================================

    dem = np.where(
        dem <= 0,
        np.nan,
        dem
    )

    # =====================================
    # HITUNG SLOPE
    # =====================================

    gy, gx = np.gradient(dem)

    slope = np.sqrt(
        gx**2 + gy**2
    )

    # =====================================
    # NORMALISASI
    # =====================================

    elev_norm = (
        np.nanmax(dem) - dem
    ) / (
        np.nanmax(dem) - np.nanmin(dem)
    )

    slope_norm = slope / np.nanmax(slope)

    # =====================================
    # FLOOD RISK
    # =====================================

    flood_risk = (
        (elev_norm * 0.75) +
        (slope_norm * 0.25)
    )

    # =====================================
    # KLASIFIKASI
    # =====================================

    risk_class = np.digitize(
        flood_risk,
        bins=[0.33, 0.66]
    ) + 1

    # =====================================
    # STATISTIK
    # =====================================

    total = np.count_nonzero(
        ~np.isnan(risk_class)
    )

    rendah = np.count_nonzero(
        risk_class == 1
    )

    sedang = np.count_nonzero(
        risk_class == 2
    )

    tinggi = np.count_nonzero(
        risk_class == 3
    )

    p_rendah = (rendah / total) * 100
    p_sedang = (sedang / total) * 100
    p_tinggi = (tinggi / total) * 100

    st.success("Analisis selesai!")

    # =====================================
    # METRICS
    # =====================================

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Risiko Rendah",
        f"{p_rendah:.1f}%"
    )

    col2.metric(
        "Risiko Sedang",
        f"{p_sedang:.1f}%"
    )

    col3.metric(
        "Risiko Tinggi",
        f"{p_tinggi:.1f}%"
    )

    # =====================================
    # VISUALISASI
    # =====================================

    st.subheader("🗺️ Flood Risk Map")

    fig, ax = plt.subplots(
        figsize=(10, 10)
    )

    im = ax.imshow(
        risk_class,
        cmap="RdYlGn_r"
    )

    ax.set_title(
        f"Flood Risk Map - {kecamatan_pilih}, {kabupaten}",
        fontsize=18
    )

    cbar = plt.colorbar(im)

    cbar.set_label(
        "1=Rendah, 2=Sedang, 3=Tinggi",
        fontsize=12
    )

    st.pyplot(fig)
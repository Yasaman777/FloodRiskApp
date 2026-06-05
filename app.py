import streamlit as st
import geopandas as gpd
import rasterio
from rasterio.mask import mask
from rasterio.warp import reproject
from rasterio.enums import Resampling
import numpy as np
import matplotlib.pyplot as plt
import os
import zipfile
import gdown
from pysheds.grid import Grid
from scipy.ndimage import distance_transform_edt

st.set_page_config(
    page_title="Flood Risk Mapping App",
    page_icon="🌊",
    layout="wide"
)

st.markdown("""
<style>
.block-container { padding-top: 2rem; }
h1, h2, h3 { color: #0f172a; }
</style>
""", unsafe_allow_html=True)

DEM_ID = "1Y23GSWnk8Rss0iFTc8ZwxN84j4dvfy4d"
SHP_ID = "1EiZSbdr31IDsANsu8_mpjrRwdBWHIy8c"
LULC_ID = "1d4BPrN-DzZZoDnIS_ICBiK7Nf-hwNeUz"

os.makedirs("data", exist_ok=True)

dem_path = "data/dem_jabar.tif"
lulc_path = "data/lulc_jabar.tif"
zip_path = "data/batas_kecamatan.zip"
extract_path = "data/shapefile"
clipped_path = "data/dem_clipped_temp.tif"

if not os.path.exists(dem_path):
    st.info("Downloading DEM Jawa Barat...")
    gdown.download(f"https://drive.google.com/uc?id={DEM_ID}", dem_path, quiet=False)

if not os.path.exists(lulc_path):
    st.info("Downloading LULC Jawa Barat...")
    gdown.download(f"https://drive.google.com/uc?id={LULC_ID}", lulc_path, quiet=False)

if not os.path.exists(zip_path):
    st.info("Downloading batas kecamatan...")
    gdown.download(f"https://drive.google.com/uc?id={SHP_ID}", zip_path, quiet=False)

if not os.path.exists(extract_path):
    os.makedirs(extract_path, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(extract_path)

shp_file = None
for root, dirs, files in os.walk(extract_path):
    for file in files:
        if file.lower().endswith(".shp"):
            shp_file = os.path.join(root, file)

if shp_file is None:
    st.error("Shapefile tidak ditemukan.")
    st.stop()

batas = gpd.read_file(shp_file)
batas = batas.dropna(subset=["WADMKC", "WADMKK"])

st.sidebar.title("🌊 Flood Risk Analysis")
st.sidebar.write("Pilih kecamatan dan kabupaten/kota.")

daftar_kecamatan = sorted(batas["WADMKC"].astype(str).unique())
kecamatan_pilih = st.sidebar.selectbox("Pilih Kecamatan", daftar_kecamatan)

data_kabupaten = batas[batas["WADMKC"].astype(str) == kecamatan_pilih]
daftar_kabupaten = sorted(data_kabupaten["WADMKK"].astype(str).unique())
kabupaten_pilih = st.sidebar.selectbox("Pilih Kabupaten/Kota", daftar_kabupaten)

wilayah = batas[
    (batas["WADMKC"].astype(str) == kecamatan_pilih) &
    (batas["WADMKK"].astype(str) == kabupaten_pilih)
]

st.sidebar.markdown("---")
st.sidebar.subheader("📊 Bobot Model")

st.sidebar.write("Flow Accumulation : 20%")
st.sidebar.write("Distance to Stream : 25%")
st.sidebar.write("Slope : 10%")
st.sidebar.write("Elevation : 10%")
st.sidebar.write("Land Cover (ESA) : 15%")
st.sidebar.write("TWI : 20%")

st.title("🌊 Flood Risk Mapping App")

st.write("""
WebGIS analisis kerawanan banjir berbasis DEM,
real flow accumulation, distance to stream, slope, dan elevation.
""")

st.info("""
Metodologi:
1. Clipping DEM berdasarkan batas kecamatan
2. Sink filling dan depression filling
3. Flow direction dan real flow accumulation
4. Stream network extraction
5. Distance to stream
6. Slope analysis
7. Weighted overlay
""")

if st.button("🚀 Proses Flood Risk"):

    if wilayah.empty:
        st.error("Wilayah tidak ditemukan.")
        st.stop()

    st.success(f"Analisis wilayah: {kecamatan_pilih}, {kabupaten_pilih}")

    with st.spinner("Memotong DEM sesuai batas kecamatan..."):

        with rasterio.open(dem_path) as src:
            wilayah = wilayah.to_crs(src.crs)

            clipped_dem, clipped_transform = mask(
                src,
                wilayah.geometry,
                crop=True,
                nodata=-9999
            )

            clipped_profile = src.profile.copy()

        clipped_dem = clipped_dem[0].astype(float)

        clipped_profile.update({
            "height": clipped_dem.shape[0],
            "width": clipped_dem.shape[1],
            "transform": clipped_transform,
            "nodata": -9999,
            "dtype": "float32"
        })

        with rasterio.open(clipped_path, "w", **clipped_profile) as dst:
            dst.write(clipped_dem.astype("float32"), 1)
    # ==========================
    # CLIP ESA WORLD COVER
    # ==========================

    with rasterio.open(lulc_path) as lulc_src:

        wilayah_lulc = wilayah.to_crs(lulc_src.crs)

        lulc_clip, lulc_transform = mask(
            lulc_src,
            wilayah_lulc.geometry,
            crop=True,
            nodata=0
        )

        lulc_clip = lulc_clip[0]

        lulc_aligned = np.empty(
            clipped_dem.shape,
            dtype=np.float32
        )

        reproject(
            source=lulc_clip,
            destination=lulc_aligned,
            src_transform=lulc_transform,
            src_crs=lulc_src.crs,
            dst_transform=clipped_transform,
            dst_crs=src.crs,
            resampling=Resampling.nearest
        )

    lulc_data = lulc_aligned.copy()
    
    with st.spinner("Menghitung flow accumulation dan stream network..."):

        grid = Grid.from_raster(clipped_path)
        dem = grid.read_raster(clipped_path)

        dem_array = np.array(dem, dtype=float)
        valid_mask = np.isfinite(dem_array) & (dem_array > -1000)

        if np.count_nonzero(valid_mask) == 0:
            st.error("DEM tidak tersedia pada wilayah ini.")
            st.stop()

        pit_filled = grid.fill_pits(dem)
        flooded = grid.fill_depressions(pit_filled)
        inflated = grid.resolve_flats(flooded)

        flow_dir = grid.flowdir(inflated)
        flow_acc = grid.accumulation(flow_dir)

    with st.spinner("Menghitung distance to stream, slope, dan flood risk..."):

        dem_clean = dem_array.copy()
        dem_clean[~valid_mask] = np.nan

        dem_filled = np.nan_to_num(
            dem_clean,
            nan=np.nanmean(dem_clean)
        )

        gy, gx = np.gradient(dem_filled)

        slope_deg = np.degrees(
            np.arctan(np.sqrt(gx**2 + gy**2))
        )
        # ==========================
        # TOPOGRAPHIC WETNESS INDEX
        # ==========================

        safe_slope = slope_deg.copy()
        safe_slope[safe_slope < 0.1] = 0.1

        twi = np.log(
            (flow_acc + 1) /
            np.tan(np.radians(safe_slope))
        )

        twi[~valid_mask] = np.nan

        valid_flow = flow_acc[valid_mask]

        stream_threshold = np.nanpercentile(valid_flow, 93)
        stream_network = (flow_acc >= stream_threshold) & valid_mask

        distance_to_stream = distance_transform_edt(~stream_network)
        distance_to_stream[~valid_mask] = np.nan

        elev_class = np.full(dem_array.shape, np.nan)
        slope_class = np.full(dem_array.shape, np.nan)
        flow_class = np.full(dem_array.shape, np.nan)
        distance_class = np.full(dem_array.shape, np.nan)
        lulc_class = np.full(dem_array.shape, np.nan)
        twi_class = np.full(dem_array.shape, np.nan)

        elev_class[(dem_clean <= 700) & valid_mask] = 3
        elev_class[(dem_clean > 700) & (dem_clean <= 1200) & valid_mask] = 2
        elev_class[(dem_clean > 1200) & valid_mask] = 1

        slope_class[(slope_deg <= 5) & valid_mask] = 3
        slope_class[(slope_deg > 5) & (slope_deg <= 15) & valid_mask] = 2
        slope_class[(slope_deg > 15) & valid_mask] = 1

        q1 = np.nanpercentile(valid_flow, 85)
        q2 = np.nanpercentile(valid_flow, 97)

        flow_class[(flow_acc < q1) & valid_mask] = 1
        flow_class[(flow_acc >= q1) & (flow_acc < q2) & valid_mask] = 2
        flow_class[(flow_acc >= q2) & valid_mask] = 3

        valid_distance = distance_to_stream[valid_mask]

        # ==========================
        # ESA WORLDCOVER CLASSIFICATION
        # ==========================

        # High flood susceptibility
        lulc_class[lulc_data == 50] = 3
        lulc_class[lulc_data == 80] = 3
        lulc_class[lulc_data == 90] = 3

        # Medium susceptibility
        lulc_class[lulc_data == 40] = 2
        lulc_class[lulc_data == 30] = 2

        # Low susceptibility
        lulc_class[lulc_data == 10] = 1
        lulc_class[lulc_data == 20] = 1
        lulc_class[lulc_data == 60] = 1
        lulc_class[lulc_data == 95] = 1
        lulc_class[lulc_data == 100] = 1

        lulc_class[~valid_mask] = np.nan
	
        # ==========================
        # DISTANCE CLASSIFICATION
        # ==========================

        distance_class[
            (distance_to_stream <= 100)
            & valid_mask
        ] = 3

        distance_class[
            (distance_to_stream > 100)
            & (distance_to_stream <= 300)
            & valid_mask
        ] = 2

        distance_class[
            (distance_to_stream > 300)
            & valid_mask
        ] = 1

        # ==========================
        # TWI CLASSIFICATION
        # ==========================

        valid_twi = twi[valid_mask]

        t1 = np.nanpercentile(valid_twi, 33)
        t2 = np.nanpercentile(valid_twi, 66)

        twi_class[(twi < t1) & valid_mask] = 1
        twi_class[(twi >= t1) & (twi < t2) & valid_mask] = 2
        twi_class[(twi >= t2) & valid_mask] = 3

        flow_weight = 0.20
        distance_weight = 0.25
        slope_weight = 0.10
        elev_weight = 0.10
        lulc_weight = 0.15
        twi_weight = 0.20

        flood_risk = (
            flow_class * flow_weight +
            distance_class * distance_weight +
            slope_class * slope_weight +
            elev_class * elev_weight +
            lulc_class * lulc_weight +
            twi_class * twi_weight
        )

        risk_class = np.full(flood_risk.shape, np.nan)

        risk_class[
            (flood_risk < 2.15)
            & valid_mask
        ] = 1

        risk_class[
            (flood_risk >= 2.15)
            & (flood_risk < 2.55)
            & valid_mask
        ] = 2

        risk_class[
            (flood_risk >= 2.55)
            & valid_mask
        ] = 3

        print("Risk shape:", risk_class.shape)
        print("DEM shape:", clipped_dem.shape)

        risk_output = risk_class.astype(np.float32)

        risk_tif = "data/flood_risk_result.tif"

        risk_profile = clipped_profile.copy()

        risk_profile.update({
            "count": 1,
            "dtype": "float32",
            "nodata": -9999
        })

        with rasterio.open(
            risk_tif,
            "w",
            **risk_profile
        ) as dst:

            out_data = np.where(
                np.isnan(risk_output),
                -9999,
                risk_output
            )

            dst.write(
                out_data.astype(np.float32),
                1
            )

    valid_pixels = risk_class[~np.isnan(risk_class)]

    rendah = np.count_nonzero(valid_pixels == 1)
    sedang = np.count_nonzero(valid_pixels == 2)
    tinggi = np.count_nonzero(valid_pixels == 3)

    total = len(valid_pixels)

    p_rendah = rendah / total * 100
    p_sedang = sedang / total * 100
    p_tinggi = tinggi / total * 100

    st.success("Analisis selesai!")

    with open(
        risk_tif,
        "rb"
    ) as file:

        st.download_button(
            label="📥 Download Flood Risk GeoTIFF",
            data=file,
            file_name=f"FloodRisk_{kecamatan_pilih}.tif",
            mime="application/octet-stream"
        )

    col1, col2, col3 = st.columns(3)
    col1.metric("Risiko Rendah", f"{p_rendah:.1f}%")
    col2.metric("Risiko Sedang", f"{p_sedang:.1f}%")
    col3.metric("Risiko Tinggi", f"{p_tinggi:.1f}%")

    # Luas piksel DEM (8.3 m x 8.3 m)
    pixel_size = 8.34
    pixel_area_km2 = (pixel_size ** 2) / 1000000

    luas_rendah = rendah * pixel_area_km2
    luas_sedang = sedang * pixel_area_km2
    luas_tinggi = tinggi * pixel_area_km2

    st.subheader("📏 Luas Area Risiko")

    st.write(f"🟢 Risiko Rendah : {luas_rendah:.2f} km²")
    st.write(f"🟡 Risiko Sedang : {luas_sedang:.2f} km²")
    st.write(f"🔴 Risiko Tinggi : {luas_tinggi:.2f} km²")

    st.subheader("🗺️ Hasil Analisis")

    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
        "Flood Risk Map",
        "DEM Clipped",
        "Slope",
        "Flow Accumulation",
        "Stream Network",
        "Distance to Stream",
        "TWI",
        "ESA Land Cover"
    ])

    with tab1:
        fig, ax = plt.subplots(figsize=(10, 8))

        masked_risk = np.ma.masked_invalid(risk_class)

        cmap = plt.cm.RdYlGn_r.copy()
        cmap.set_bad(color="white")

        im = ax.imshow(masked_risk, cmap=cmap, vmin=1, vmax=3)

        ax.contour(
            stream_network,
            levels=[0.5],
            colors="blue",
            linewidths=0.5
        )

        ax.set_title(
            f"Flood Risk Map - {kecamatan_pilih}, {kabupaten_pilih}",
            fontsize=16
        )

        ax.axis("off")
        cbar = plt.colorbar(im, ax=ax)
        cbar.set_label("1=Rendah | 2=Sedang | 3=Tinggi")

        st.pyplot(fig)

        png_path = f"data/FloodRisk_{kecamatan_pilih}.png"

        fig.savefig(
            png_path,
            dpi=300,
            bbox_inches="tight"
        )

        with open(png_path, "rb") as f:

            st.download_button(
            label="📷 Download Flood Risk PNG",
            data=f,
            file_name=f"FloodRisk_{kecamatan_pilih}.png",
            mime="image/png"
        )

        st.markdown("""
        **Keterangan Flood Risk:**
        - 🟢 Hijau = Risiko rendah  
        - 🟡 Kuning = Risiko sedang  
        - 🔴 Merah = Risiko tinggi  
        - 🔵 Garis biru = Stream network  
        - Putih = Area luar kecamatan / NoData  
        """)

    with tab2:
        fig_dem, ax_dem = plt.subplots(figsize=(10, 8))

        dem_plot = dem_clean.copy()

        im_dem = ax_dem.imshow(dem_plot, cmap="terrain")

        ax_dem.set_title(
            f"DEM Clipped - {kecamatan_pilih}, {kabupaten_pilih}",
            fontsize=16
        )

        ax_dem.axis("off")
        cbar_dem = plt.colorbar(im_dem, ax=ax_dem)
        cbar_dem.set_label("Elevation")

        st.pyplot(fig_dem)

    with tab3:
        fig_slope, ax_slope = plt.subplots(figsize=(10, 8))

        slope_plot = slope_deg.copy()
        slope_plot[~valid_mask] = np.nan

        im_slope = ax_slope.imshow(slope_plot, cmap="terrain")

        ax_slope.set_title(
            f"Slope Map - {kecamatan_pilih}, {kabupaten_pilih}",
            fontsize=16
        )

        ax_slope.axis("off")
        cbar_slope = plt.colorbar(im_slope, ax=ax_slope)
        cbar_slope.set_label("Slope Degree")

        st.pyplot(fig_slope)

    with tab4:
        fig_flow, ax_flow = plt.subplots(figsize=(10, 8))

        flow_plot = np.log1p(flow_acc)
        flow_plot = np.where(valid_mask, flow_plot, np.nan)

        im_flow = ax_flow.imshow(flow_plot, cmap="Blues")

        ax_flow.set_title(
            f"Real Flow Accumulation - {kecamatan_pilih}, {kabupaten_pilih}",
            fontsize=16
        )

        ax_flow.axis("off")
        cbar_flow = plt.colorbar(im_flow, ax=ax_flow)
        cbar_flow.set_label("Log Flow Accumulation")

        st.pyplot(fig_flow)

    with tab5:
        fig_stream, ax_stream = plt.subplots(figsize=(10, 8))

        background = np.where(valid_mask, 1, np.nan)

        ax_stream.imshow(
            background,
            cmap="Greys",
            alpha=0.15
        )

        stream_plot = np.where(stream_network, 1, np.nan)

        ax_stream.imshow(
            stream_plot,
            cmap="Blues",
            alpha=1.0,
            vmin=0,
            vmax=1
        )

        ax_stream.contour(
            stream_network,
            levels=[0.5],
            colors="blue",
            linewidths=1.2
        )

        ax_stream.set_title(
            f"Stream Network - {kecamatan_pilih}, {kabupaten_pilih}",
            fontsize=16
        )

        ax_stream.axis("off")

        st.pyplot(fig_stream)

        st.markdown("""
        **Keterangan Stream Network:**
        Stream network diekstraksi dari piksel dengan nilai flow accumulation tertinggi,
        yaitu percentile 97 pada wilayah kecamatan yang dianalisis.
        """)

    with tab6:
        fig_dist, ax_dist = plt.subplots(figsize=(10, 8))

        dist_plot = distance_to_stream.copy()
        dist_plot[~valid_mask] = np.nan

        im_dist = ax_dist.imshow(dist_plot, cmap="viridis_r")

        ax_dist.contour(
            stream_network,
            levels=[0.5],
            colors="blue",
            linewidths=0.8
        )

        ax_dist.set_title(
            f"Distance to Stream - {kecamatan_pilih}, {kabupaten_pilih}",
            fontsize=16
        )

        ax_dist.axis("off")

        cbar_dist = plt.colorbar(im_dist, ax=ax_dist)
        cbar_dist.set_label("Pixel Distance to Stream")

        st.pyplot(fig_dist)

        st.markdown("""
        **Keterangan Distance to Stream:**
        - Nilai kecil = dekat dengan stream/aliran utama  
        - Nilai besar = jauh dari stream  
        - Semakin dekat ke stream, semakin tinggi potensi kerawanan banjir  
        """)

    with tab7:

        fig_twi, ax_twi = plt.subplots(figsize=(10,8))

        twi_plot = twi.copy()
        twi_plot[~valid_mask] = np.nan

        im_twi = ax_twi.imshow(
            twi_plot,
            cmap="YlGnBu"
        )

        ax_twi.set_title(
            f"TWI - {kecamatan_pilih}, {kabupaten_pilih}"
        )

        ax_twi.axis("off")

        cbar_twi = plt.colorbar(
            im_twi,
            ax=ax_twi
        )

        cbar_twi.set_label("TWI")

        st.pyplot(fig_twi)

    with tab8:

        fig_lulc, ax_lulc = plt.subplots(
            figsize=(10,8)
        )

        lulc_plot = lulc_data.copy()

        lulc_plot[~valid_mask] = np.nan

        im_lulc = ax_lulc.imshow(
            lulc_plot,
            cmap="tab20"
        )

        ax_lulc.set_title(
            f"ESA WorldCover - {kecamatan_pilih}, {kabupaten_pilih}"
        )

        ax_lulc.axis("off")

        cbar_lulc = plt.colorbar(
            im_lulc,
            ax=ax_lulc
        )

        cbar_lulc.set_label(
            "ESA Class"
        )

        st.pyplot(fig_lulc)

        st.markdown("""
        **ESA WorldCover Classes**
    
        10 = Tree Cover  
        20 = Shrubland  
        30 = Grassland  
        40 = Cropland  
        50 = Built-up  
        60 = Bare/Sparse Vegetation  
        80 = Permanent Water  
        90 = Herbaceous Wetland  
        95 = Mangroves  
        100 = Moss/Lichen
        """)
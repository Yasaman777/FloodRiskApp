import io
import streamlit as st
import geopandas as gpd
import rasterio
from rasterio.mask import mask
import numpy as np
import matplotlib.pyplot as plt
from pysheds.grid import Grid

# =====================================
# PAGE CONFIG
# =====================================
st.set_page_config(
    page_title="Flood Risk Mapping App",
    page_icon="🌊",
    layout="wide"
)

# =====================================
# CSS STYLE
# =====================================
st.markdown("""
<style>
.block-container {
    padding-top: 2rem;
    padding-bottom: 2rem;
}

.main-title {
    font-size: 42px;
    font-weight: 800;
    color: #0F172A;
}

.subtitle {
    font-size: 18px;
    color: #475569;
}

.info-card {
    padding: 18px;
    border-radius: 14px;
    background-color: #F8FAFC;
    border: 1px solid #E2E8F0;
    margin-bottom: 16px;
}
</style>
""", unsafe_allow_html=True)

# =====================================
# HEADER
# =====================================
st.markdown(
    '<div class="main-title">🌊 Flood Risk Mapping App</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="subtitle">Aplikasi pemetaan kerawanan banjir berbasis DEM, slope, elevation, dan flow accumulation.</div>',
    unsafe_allow_html=True
)

st.write("")

# =====================================
# DATA PATH
# =====================================
dem_path = "data/dem_jabar.tif"
shp_path = "data/batas_kecamatan.shp"

# =====================================
# LOAD SHAPEFILE
# =====================================
batas = gpd.read_file(shp_path)

# =====================================
# SIDEBAR
# =====================================
st.sidebar.title("⚙️ Parameter Analisis")

st.sidebar.write(
    "Pilih wilayah yang ingin dianalisis."
)

daftar_kecamatan = sorted(
    batas["WADMKC"]
    .dropna()
    .astype(str)
    .unique()
)

kecamatan = st.sidebar.selectbox(
    "Pilih Kecamatan",
    daftar_kecamatan
)

data_kabupaten = batas[
    batas["WADMKC"] == kecamatan
]

daftar_kabupaten = sorted(
    data_kabupaten["WADMKK"]
    .dropna()
    .astype(str)
    .unique()
)

kabupaten = st.sidebar.selectbox(
    "Pilih Kabupaten/Kota",
    daftar_kabupaten
)

st.sidebar.markdown("---")

st.sidebar.write("Bobot Analisis")
st.sidebar.write("Flow Accumulation : 50%")
st.sidebar.write("Slope : 25%")
st.sidebar.write("Elevation : 25%")

# =====================================
# INFO CARD
# =====================================
st.markdown("""
<div class="info-card">
<b>Metode:</b><br>
Aplikasi ini melakukan pemotongan DEM berdasarkan batas kecamatan,
kemudian menghitung flow accumulation, slope, dan elevasi.
Ketiga parameter tersebut digabungkan menggunakan weighted overlay
untuk menghasilkan peta kerawanan banjir.
</div>
""", unsafe_allow_html=True)

# =====================================
# BUTTON
# =====================================
if st.button("🚀 Proses Flood Risk Map"):

    wilayah = batas[
        (batas["WADMKC"] == kecamatan) &
        (batas["WADMKK"] == kabupaten)
    ]

    if wilayah.empty:

        st.error("Wilayah tidak ditemukan.")

    else:

        st.success(
            f"Wilayah ditemukan: {kecamatan}, {kabupaten}"
        )

        # =====================================
        # CLIP DEM
        # =====================================
        with st.spinner(
            "Memotong DEM sesuai batas kecamatan..."
        ):

            with rasterio.open(dem_path) as src:

                wilayah = wilayah.to_crs(src.crs)

                clipped_dem, clipped_transform = mask(
                    src,
                    wilayah.geometry,
                    crop=True,
                    nodata=-9999
                )

                clipped_profile = src.profile.copy()

            clipped_dem = clipped_dem[0]

            clipped_profile.update({
                "height": clipped_dem.shape[0],
                "width": clipped_dem.shape[1],
                "transform": clipped_transform,
                "nodata": -9999
            })

            clipped_path = "data/dem_clipped_temp.tif"

            with rasterio.open(
                clipped_path,
                "w",
                **clipped_profile
            ) as dst:

                dst.write(
                    clipped_dem.astype(
                        rasterio.float32
                    ),
                    1
                )

        # =====================================
        # HYDROLOGY ANALYSIS
        # =====================================
        with st.spinner(
            "Menghitung flood risk..."
        ):

            grid = Grid.from_raster(
                clipped_path
            )

            dem = grid.read_raster(
                clipped_path
            )

            dem_array = np.array(
                dem,
                dtype=float
            )

            valid_mask = (
                np.isfinite(dem_array)
            ) & (
                dem_array > -1000
            )

            pit_filled = grid.fill_pits(dem)

            flooded = grid.fill_depressions(
                pit_filled
            )

            inflated = grid.resolve_flats(
                flooded
            )

            flow_dir = grid.flowdir(
                inflated
            )

            flow_acc = grid.accumulation(
                flow_dir
            )

            dx, dy = np.gradient(
                inflated
            )

            slope_deg = np.degrees(
                np.arctan(
                    np.sqrt(dx**2 + dy**2)
                )
            )

            # =====================================
            # RECLASS SLOPE
            # =====================================
            slope_class = np.full(
                slope_deg.shape,
                np.nan
            )

            slope_class[
                (slope_deg <= 15) &
                valid_mask
            ] = 3

            slope_class[
                (slope_deg > 15) &
                (slope_deg <= 30) &
                valid_mask
            ] = 2

            slope_class[
                (slope_deg > 30) &
                valid_mask
            ] = 1

            # =====================================
            # RECLASS ELEVATION
            # =====================================
            elev_class = np.full(
                dem_array.shape,
                np.nan
            )

            elev_class[
                (dem_array <= 1100) &
                valid_mask
            ] = 3

            elev_class[
                (dem_array > 1100) &
                (dem_array <= 1600) &
                valid_mask
            ] = 2

            elev_class[
                (dem_array > 1600) &
                valid_mask
            ] = 1

            # =====================================
            # RECLASS FLOW ACCUMULATION
            # =====================================
            flow_class = np.full(
                flow_acc.shape,
                np.nan
            )

            flow_class[
                (flow_acc <= 1000) &
                valid_mask
            ] = 1

            flow_class[
                (flow_acc > 1000) &
                (flow_acc <= 10000) &
                valid_mask
            ] = 2

            flow_class[
                (flow_acc > 10000) &
                valid_mask
            ] = 3

            # =====================================
            # WEIGHTED OVERLAY
            # =====================================
            flood_risk = (
                (flow_class * 0.5) +
                (slope_class * 0.25) +
                (elev_class * 0.25)
            )

            flood_class = np.full(
                flood_risk.shape,
                np.nan
            )

            flood_class[
                (flood_risk < 1.5) &
                valid_mask
            ] = 1

            flood_class[
                (flood_risk >= 1.5) &
                (flood_risk < 2.0) &
                valid_mask
            ] = 2

            flood_class[
                (flood_risk >= 2.0) &
                valid_mask
            ] = 3

            flood_class[
                ~valid_mask
            ] = np.nan

            # =====================================
            # STREAM NETWORK
            # =====================================
            stream = (
                flow_acc > 200
            ) & valid_mask

            stream_plot = np.where(
                stream,
                1,
                np.nan
            )

        st.success("Analisis selesai!")

        # =====================================
        # METRICS
        # =====================================
        valid_pixels = flood_class[
            ~np.isnan(flood_class)
        ]

        low_pct = (
            np.sum(valid_pixels == 1)
            / len(valid_pixels)
            * 100
        )

        med_pct = (
            np.sum(valid_pixels == 2)
            / len(valid_pixels)
            * 100
        )

        high_pct = (
            np.sum(valid_pixels == 3)
            / len(valid_pixels)
            * 100
        )

        col1, col2, col3 = st.columns(3)

        col1.metric(
            "Risiko Rendah",
            f"{low_pct:.1f}%"
        )

        col2.metric(
            "Risiko Sedang",
            f"{med_pct:.1f}%"
        )

        col3.metric(
            "Risiko Tinggi",
            f"{high_pct:.1f}%"
        )

        # =====================================
        # TABS
        # =====================================
        st.subheader("🗺️ Hasil Analisis")

        tab1, tab2, tab3, tab4 = st.tabs([
            "Flood Risk Map",
            "DEM Clipped",
            "Flow Accumulation",
            "Stream Network"
        ])

        # =====================================
        # TAB 1
        # =====================================
        with tab1:

            fig, ax = plt.subplots(
                figsize=(10, 8)
            )

            masked_flood = np.ma.masked_invalid(
                flood_class
            )

            cmap = plt.cm.RdYlGn_r.copy()

            cmap.set_bad(color="white")

            im = ax.imshow(
                masked_flood,
                cmap=cmap,
                vmin=1,
                vmax=3
            )

            ax.set_title(
                f"Flood Risk Map - {kecamatan}, {kabupaten}",
                fontsize=16
            )

            ax.axis("off")

            fig.colorbar(
                im,
                ax=ax,
                label="1=Rendah, 2=Sedang, 3=Tinggi"
            )

            fig.tight_layout()

            st.pyplot(
                fig,
                use_container_width=True
            )

            # DOWNLOAD PNG
            buf = io.BytesIO()

            fig.savefig(
                buf,
                format="png",
                dpi=300,
                bbox_inches="tight"
            )

            buf.seek(0)

            st.download_button(
                label="⬇️ Download Flood Risk Map",
                data=buf,
                file_name=f"flood_risk_{kecamatan}_{kabupaten}.png",
                mime="image/png"
            )

            # LEGEND
            st.subheader(
                "Keterangan Flood Risk"
            )

            st.markdown("""
            - 🟢 Hijau : Risiko rendah  
            - 🟡 Kuning : Risiko sedang  
            - 🔴 Merah : Risiko tinggi  
            """)

        # =====================================
        # TAB 2
        # =====================================
        with tab2:

            dem_plot = dem_array.copy()

            dem_plot[
                ~valid_mask
            ] = np.nan

            fig_dem, ax_dem = plt.subplots(
                figsize=(10, 8)
            )

            im_dem = ax_dem.imshow(
                dem_plot,
                cmap="terrain"
            )

            ax_dem.set_title(
                f"DEM Clipped - {kecamatan}, {kabupaten}",
                fontsize=16
            )

            ax_dem.axis("off")

            fig_dem.colorbar(
                im_dem,
                ax=ax_dem,
                label="Elevation"
            )

            fig_dem.tight_layout()

            st.pyplot(
                fig_dem,
                use_container_width=True
            )

            st.subheader(
                "Keterangan DEM"
            )

            st.markdown("""
            - Warna terang menunjukkan elevasi lebih tinggi  
            - Warna gelap menunjukkan elevasi lebih rendah  
            """)

        # =====================================
        # TAB 3
        # =====================================
        with tab3:

            flow_acc_plot = np.log1p(
                flow_acc
            )

            flow_acc_plot = np.where(
                valid_mask,
                flow_acc_plot,
                np.nan
            )

            fig_flow, ax_flow = plt.subplots(
                figsize=(10, 8)
            )

            im_flow = ax_flow.imshow(
                flow_acc_plot,
                cmap="Blues"
            )

            ax_flow.set_title(
                "Flow Accumulation",
                fontsize=16
            )

            ax_flow.axis("off")

            fig_flow.colorbar(
                im_flow,
                ax=ax_flow,
                label="Log Flow Accumulation"
            )

            fig_flow.tight_layout()

            st.pyplot(
                fig_flow,
                use_container_width=True
            )

            st.subheader(
                "Keterangan Flow Accumulation"
            )

            st.markdown("""
            - Biru terang menunjukkan akumulasi aliran tinggi  
            - Area tersebut berpotensi menjadi jalur aliran air  
            """)

        # =====================================
        # TAB 4
        # =====================================
        with tab4:

            fig_stream, ax_stream = plt.subplots(
                figsize=(10, 8)
            )

            ax_stream.imshow(
                stream_plot,
                cmap="Blues"
            )

            ax_stream.set_title(
                "Stream Network",
                fontsize=16
            )

            ax_stream.axis("off")

            fig_stream.tight_layout()

            st.pyplot(
                fig_stream,
                use_container_width=True
            )

            st.subheader(
                "Keterangan Stream Network"
            )

            st.markdown("""
            - Garis biru menunjukkan jaringan aliran sungai hasil ekstraksi otomatis  
            """)
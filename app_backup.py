import streamlit as st
import geopandas as gpd
import rasterio
from rasterio.mask import mask
import numpy as np
import matplotlib.pyplot as plt
from pysheds.grid import Grid

st.title("Flood Risk App")
st.write("Pilih kecamatan dan kabupaten, lalu sistem akan membuat Flood Risk Map otomatis.")

dem_path = "data/dem_jabar.tif"
shp_path = "data/batas_kecamatan.shp"

batas = gpd.read_file(shp_path)

daftar_kecamatan = sorted(batas["WADMKC"].dropna().astype(str).unique())
kecamatan = st.selectbox("Pilih Kecamatan", daftar_kecamatan)

data_kabupaten = batas[batas["WADMKC"] == kecamatan]
daftar_kabupaten = sorted(data_kabupaten["WADMKK"].dropna().astype(str).unique())
kabupaten = st.selectbox("Pilih Kabupaten/Kota", daftar_kabupaten)

if st.button("Proses Flood Risk Map"):

    wilayah = batas[
        (batas["WADMKC"] == kecamatan) &
        (batas["WADMKK"] == kabupaten)
    ]

    if wilayah.empty:
        st.error("Wilayah tidak ditemukan.")
    else:
        st.success(f"Wilayah ditemukan: {kecamatan}, {kabupaten}")

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

            clipped_dem = clipped_dem[0]

            clipped_profile.update({
                "height": clipped_dem.shape[0],
                "width": clipped_dem.shape[1],
                "transform": clipped_transform,
                "nodata": -9999
            })

            clipped_path = "data/dem_clipped_temp.tif"

            with rasterio.open(clipped_path, "w", **clipped_profile) as dst:
                dst.write(clipped_dem.astype(rasterio.float32), 1)

        with st.spinner("Menghitung flow accumulation, slope, dan flood risk..."):

            grid = Grid.from_raster(clipped_path)
            dem = grid.read_raster(clipped_path)

            dem_array = np.array(dem, dtype=float)
            valid_mask = np.isfinite(dem_array) & (dem_array > -1000)

            pit_filled = grid.fill_pits(dem)
            flooded = grid.fill_depressions(pit_filled)
            inflated = grid.resolve_flats(flooded)

            flow_dir = grid.flowdir(inflated)
            flow_acc = grid.accumulation(flow_dir)

            dx, dy = np.gradient(inflated)
            slope_deg = np.degrees(np.arctan(np.sqrt(dx**2 + dy**2)))

            slope_class = np.full(slope_deg.shape, np.nan)
            slope_class[(slope_deg <= 15) & valid_mask] = 3
            slope_class[(slope_deg > 15) & (slope_deg <= 30) & valid_mask] = 2
            slope_class[(slope_deg > 30) & valid_mask] = 1

            elev_class = np.full(dem_array.shape, np.nan)
            elev_class[(dem_array <= 1100) & valid_mask] = 3
            elev_class[(dem_array > 1100) & (dem_array <= 1600) & valid_mask] = 2
            elev_class[(dem_array > 1600) & valid_mask] = 1

            flow_class = np.full(flow_acc.shape, np.nan)
            flow_class[(flow_acc <= 1000) & valid_mask] = 1
            flow_class[(flow_acc > 1000) & (flow_acc <= 10000) & valid_mask] = 2
            flow_class[(flow_acc > 10000) & valid_mask] = 3

            flood_risk = (
                (flow_class * 0.5) +
                (slope_class * 0.25) +
                (elev_class * 0.25)
            )

            flood_class = np.full(flood_risk.shape, np.nan)
            flood_class[(flood_risk < 1.5) & valid_mask] = 1
            flood_class[(flood_risk >= 1.5) & (flood_risk < 2.0) & valid_mask] = 2
            flood_class[(flood_risk >= 2.0) & valid_mask] = 3
            flood_class[~valid_mask] = np.nan

        st.success("Analisis selesai!")

        fig, ax = plt.subplots(figsize=(8, 6))

        masked_flood = np.ma.masked_invalid(flood_class)

        cmap = plt.cm.RdYlGn_r.copy()
        cmap.set_bad(color="white")

        im = ax.imshow(masked_flood, cmap=cmap, vmin=1, vmax=3)
        ax.set_title(f"Flood Risk Map - {kecamatan}, {kabupaten}")
        ax.axis("off")

        fig.colorbar(im, ax=ax, label="1=Rendah, 2=Sedang, 3=Tinggi")
        st.pyplot(fig)

        st.subheader("Keterangan")
        st.markdown("""
        - 🟢 Hijau: Risiko rendah  
        - 🟡 Kuning: Risiko sedang  
        - 🔴 Merah: Risiko tinggi  
        """)
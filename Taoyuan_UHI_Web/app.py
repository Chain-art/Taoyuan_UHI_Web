import streamlit as st
import ee
import folium
import geopandas as gpd
from streamlit_folium import folium_static
import datetime

# ==========================================
# 1. 網頁基本設定 (設定標題與寬版顯示)
# ==========================================
st.set_page_config(page_title="桃園市熱島效應分析", page_icon="🏙️", layout="wide")

# ==========================================
# 2. 核心功能快取區 (Cache) - 網頁順暢的秘密
# ==========================================
# 使用 @st.cache_resource 讓網頁記住登入狀態，不用每次點按鈕都重新認證
@st.cache_resource
def init_gee():
    try:
        credentials = ee.ServiceAccountCredentials(
            st.secrets["gcp_service_account"]["client_email"],
            st.secrets["gcp_service_account"]["private_key"]
        )
        ee.Initialize(credentials)
    except Exception as e:
        # 直接把真實的錯誤訊息印在網頁上，並停止程式
        st.error("⚠️ 金鑰讀取失敗，真實的錯誤訊息是：")
        st.error(e)
        st.stop()

# 使用 @st.cache_data 讓網頁記住 Shapefile，不用每次都花時間讀取硬碟
@st.cache_data
def load_shapefile(shp_path):
    gdf = gpd.read_file(shp_path, encoding='utf-8')
    return gdf.to_crs(epsg=4326)

# ==========================================
# 3. GEE 圖層綁定函數 (來自之前的無敵解法)
# ==========================================
def add_ee_layer(self, ee_image_object, vis_params, name):
    map_id_dict = ee.Image(ee_image_object).getMapId(vis_params)
    folium.raster_layers.TileLayer(
        tiles=map_id_dict['tile_fetcher'].url_format,
        attr='Map Data &copy; <a href="https://earthengine.google.com/">Google Earth Engine</a>',
        name=name,
        overlay=True,
        control=True
    ).add_to(self)
folium.Map.add_ee_layer = add_ee_layer

# ==========================================
# 4. Streamlit 網頁 UI 設計 (前端介面)
# ==========================================
st.title("🏙️ 桃園市熱島效應 (UHI) 與植被 (NDVI) 雲端分析系統")
st.markdown("本系統串接 Google Earth Engine，可即時運算 Landsat 8 衛星資料。請於左側設定參數。")

# 建立側邊欄
st.sidebar.header("⚙️ 參數設定")

# 讓使用者選擇日期範圍 (預設為我們之前測試成功的 2021 年 8 月)
start_date = st.sidebar.date_input("開始日期", datetime.date(2021, 8, 1))
end_date = st.sidebar.date_input("結束日期", datetime.date(2021, 8, 31))

# 讓使用者設定雲量容忍度 (0~100%)
cloud_tolerance = st.sidebar.slider("最高雲量容忍度 (%)", min_value=0, max_value=100, value=30, step=5)

# ⚠️ 注意：請確保這裡是你電腦中真實的 Shapefile 路徑
SHP_PATH = "C:\\Users\\chihi\\Downloads\\Landsat 8\\Shapefile\\TOWN_MOI_1140318.shp"

# ==========================================
# 5. 後端運算邏輯 (按下按鈕後才會執行)
# ==========================================
if st.sidebar.button("🚀 開始生成地圖"):
    
    # 顯示載入中的轉圈圈動畫
    with st.spinner('正在向 Google 雲端超級電腦請求資料，請稍候...'):
        try:
            # 1. 執行初始化與讀取邊界
            init_gee()
            gdf = load_shapefile(SHP_PATH)

            # 2. 建立 Folium 基礎地圖
            my_map = folium.Map(location=[24.9, 121.2], zoom_start=11)

            # 3. 將網頁的日期格式轉換為 GEE 看得懂的字串
            start_str = start_date.strftime('%Y-%m-%d')
            end_str = end_date.strftime('%Y-%m-%d')

            # 4. 向 GEE 請求資料 (加入雲量過濾器)
            image = ee.ImageCollection('LANDSAT/LC08/C02/T1_L2') \
                .filterBounds(ee.Geometry.Point([121.2, 24.9])) \
                .filterDate(start_str, end_str) \
                .filter(ee.Filter.lt('CLOUD_COVER', cloud_tolerance)) \
                .sort('CLOUD_COVER') \
                .first()

            # 5. 雲端計算 LST 與 NDVI
            lst = image.select('ST_B10').multiply(0.00341802).add(149.0).subtract(273.15).rename('LST')
            ndvi = image.normalizedDifference(['SR_B5', 'SR_B4']).rename('NDVI')

            # 6. 疊加圖層
            lst_vis = {'min': 22.0, 'max': 42.0, 'palette': ['000004', '320A5A', '781C6D', 'BC3754', 'ED6925', 'F5D259', 'FCFFA4']}
            my_map.add_ee_layer(lst, lst_vis, 'LST 地表溫度')

            ndvi_vis = {'min': -0.2, 'max': 0.8, 'palette': ['red', 'yellow', 'green']}
            my_map.add_ee_layer(ndvi, ndvi_vis, 'NDVI 植生指標')

            # 7. 疊加互動式 Shapefile 邊界
            style_function = lambda x: {'fillColor': '#000000', 'color': '#00FFFF', 'weight': 2, 'fillOpacity': 0}
            tooltip = folium.GeoJsonTooltip(fields=['COUNTYNAME', 'TOWNNAME'], aliases=['縣市：', '鄉鎮市區：'])
            folium.GeoJson(gdf, name='行政區界', style_function=style_function, tooltip=tooltip).add_to(my_map)

            my_map.add_child(folium.LayerControl())

            # 8. 將 Folium 地圖渲染至 Streamlit 網頁上
            folium_static(my_map, width=1200, height=700)
            
            st.success(f"地圖生成成功！您查看的是 {start_str} 至 {end_str} 區間內最清晰的衛星影像。")

        except Exception as e:
            st.error("⚠️ 發生錯誤！可能是該日期區間內沒有符合雲量條件的衛星影像，請嘗試擴大「日期範圍」或調高「雲量容忍度」。")
            st.exception(e)

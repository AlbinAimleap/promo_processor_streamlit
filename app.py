import streamlit as st
import json
import asyncio
import pandas as pd
from pathlib import Path
import time
from promo_processor.processor import PromoProcessor
from typing import Optional, Dict, List, Any, Callable
import logging
import os
import tempfile

class AppConfig:
    PAGE_CONFIG = {
        'page_title': "Promo Processor",
        'layout': "wide",
        'initial_sidebar_state': "expanded",
        'menu_items': {
            'Get Help': 'https://www.example.com/help',
            'Report a bug': "https://www.example.com/bug",
            'About': "Promotional Deal Processor v1.0"
        }
    }

    CUSTOM_CSS = """
        <style>
        .main { 
            padding: 2rem;
            background-color: #f8f9fa;
        }
        .stButton>button {
            width: 100%;
            border-radius: 8px;
            height: 3.2em;
            background-color: #007bff;
            color: white;
            font-weight: 500;
            transition: all 0.3s ease;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .stButton>button:hover { 
            background-color: #0056b3;
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.2);
        }
        .upload-header {
            color: #2c3e50;
            font-size: 1.8em;
            font-weight: 600;
            margin: 1.5em 0;
            padding-bottom: 0.5em;
            border-bottom: 2px solid #007bff;
        }
        .stAlert {
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }
        .file-uploader {
            border: 2px dashed #dee2e6;
            border-radius: 10px;
            padding: 2em;
            text-align: center;
            background-color: white;
            transition: all 0.3s ease;
        }
        .file-uploader:hover {
            border-color: #007bff;
        }
        .results-container {
            background-color: white;
            padding: 1.5em;
            border-radius: 10px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        .app-title {
            background: linear-gradient(45deg, #007bff, #00a6ff);
            color: white !important;
            padding: 1em;
            border-radius: 10px;
            margin-bottom: 2em;
            text-align: center;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        </style>
    """

class DataProcessor:
    @staticmethod
    def convert_to_json(uploaded_file) -> Optional[List[Dict]]:
        if not uploaded_file:
            return None

        file_extension = Path(uploaded_file.name).suffix.lower()
        file_handlers: Dict[str, Callable] = {
            '.json': lambda f: json.load(f),
            '.csv': lambda f: DataProcessor._convert_df_to_json(pd.read_csv(f)),
            '.xlsx': lambda f: DataProcessor._convert_df_to_json(pd.read_excel(f)),
            '.xls': lambda f: DataProcessor._convert_df_to_json(pd.read_excel(f))
        }

        try:
            if file_extension in file_handlers:
                st.write("Converting file to JSON...")
                return file_handlers[file_extension](uploaded_file)
            st.error("📛 Unsupported file format. Please upload JSON, CSV, or Excel file.")
            return None
        except Exception as e:
            st.error(f"❌ Error converting file: {str(e)}")
            return None

    @staticmethod
    def _convert_df_to_json(df: pd.DataFrame) -> List[Dict]:
        df.fillna("", inplace=True)
        df["crawl_date"] = df["crawl_date"].astype(str)
        return df.to_dict(orient='records')

class PromoApp:
    def __init__(self):
        self.initialize_session_state()
        self.setup_page()
        self.setup_logging()

    def setup_logging(self):
        temp_dir = tempfile.gettempdir()
        log_file = os.path.join(temp_dir, 'promo_processor.log')
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, mode='a'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def initialize_session_state():
        if "results" not in st.session_state:
            st.session_state.results = []
        if "qa_stats" not in st.session_state:
            st.session_state.qa_stats = {}

    def setup_page(self):
        st.set_page_config(**AppConfig.PAGE_CONFIG)
        st.markdown(AppConfig.CUSTOM_CSS, unsafe_allow_html=True)
        st.markdown("<div class='app-title'><h1>Promotional Deal Processor</h1></div>", 
                   unsafe_allow_html=True)

    async def process_data(self):
        if not self._has_valid_uploaded_data():
            return
        
        try:
            with st.spinner('🔄 Processing your data...'):
                await self._process_data_with_progress()
            st.success("✅ Processing completed successfully!")
            self._calculate_qa_stats()
        except Exception as e:
            st.error(f"❌ An error occurred: {str(e)}")
            self.logger.error(f"Error processing data: {str(e)}", exc_info=True)

    def _calculate_qa_stats(self):
        total_items = len(st.session_state.results)
        volume_deals = sum(1 for item in st.session_state.results if item.get('volume_deals_description'))
        volume_deals_not_processed = volume_deals - sum(1 for item in st.session_state.results if item.get('volume_deals_price'))
        digital_deals = sum(1 for item in st.session_state.results if item.get('digital_coupon_description'))
        digital_deals_not_processed = digital_deals - sum(1 for item in st.session_state.results if item.get('digital_coupon_price'))
        
        st.session_state.qa_stats = {
            'Total Items Processed': total_items,
            'Volume Deals Count': volume_deals,
            'Not Processed Volume Deals': volume_deals_not_processed,
            'Digital Coupon Count': digital_deals,
            'Not Processed Digital Coupon': digital_deals_not_processed
        }

    def save_results(self):
        if len(st.session_state.results) == 0:
            st.warning("⚠️ No results available to download")
            return

        filename = getattr(st.session_state, 'filename', 'processed_results').split('.')[0]
        json_str = json.dumps(st.session_state.results, indent=4)
        
        st.download_button(
            label="📥 Download Results",
            data=json_str.encode('utf-8'),
            file_name=f"{filename}.json",
            mime='application/json'
        )

    def render_upload_section(self):
        st.markdown("<div class='upload-header'>📤 Upload Data</div>", unsafe_allow_html=True)
        with st.container():
            uploaded_file = st.file_uploader(
                "Drag and drop your file here or click to browse",
                type=['json', 'csv', 'xlsx', 'xls'],
                help="Supported formats: JSON, CSV, Excel"
            )
            st.markdown("</div>", unsafe_allow_html=True)

            if uploaded_file:
                st.session_state.results = []
                st.session_state.qa_stats = {}
                data = DataProcessor.convert_to_json(uploaded_file)
                if data:
                    st.session_state.uploaded_data = data
                    st.session_state.filename = uploaded_file.name
                    st.success(f"✅ Successfully loaded {len(data)} records")

    async def render_action_buttons(self):
        st.markdown("<br>", unsafe_allow_html=True)
        col1, _, col2 = st.columns([1, 0.2, 1])
        with col1:
            if st.button("🔄 Process Data", key='process_button'):
                if 'uploaded_data' in st.session_state:
                    await self.process_data()
        with col2:
            if len(st.session_state.results) == 0:
                return
            st.download_button(
                label="📥 Save Results",
                data=json.dumps(st.session_state.results, indent=4).encode('utf-8'),
                file_name=f"{getattr(st.session_state, 'filename', 'processed_results').split('.')[0]}.json",
                mime='application/json',
                disabled=len(st.session_state.results) == 0
            )
            
    def render_results_section(self):
        if len(st.session_state.results) > 0:
            tab1, tab2 = st.tabs(["Results", "QA Statistics"])
            
            with tab1:
                with st.container():
                    st.markdown("<div class='results-container'>", unsafe_allow_html=True)
                    st.json(st.session_state.results)
                    st.markdown("</div>", unsafe_allow_html=True)
            
            with tab2:
                with st.container():
                    cols = st.columns(3)
                    for i, (key, value) in enumerate(st.session_state.qa_stats.items()):
                        col_index = i % 3
                        with cols[col_index]:
                            st.metric(
                                label=f"📊 {key}",
                                value=value,
                                delta=None,
                                delta_color="normal"
                            )
                           
        else:
            st.info("💡 No results to display. Upload and process data to see results here.")

    @staticmethod
    def _has_valid_uploaded_data() -> bool:
        return 'uploaded_data' in st.session_state and st.session_state.uploaded_data

    async def _process_data_with_progress(self):
        total_items = len(st.session_state.uploaded_data)
        progress_text = st.empty()
        progress_bar = st.progress(0)
        start_time = time.time()
        
        for idx, item in enumerate(st.session_state.uploaded_data):
            processor = await PromoProcessor.process_item(item)
            st.session_state.results.extend(processor.results)
            processor.results = []
            elapsed_time = time.time() - start_time
            items_per_second = (idx + 1) / elapsed_time if elapsed_time > 0 else 0
            estimated_total_time = total_items / items_per_second if items_per_second > 0 else 0
            remaining_time = estimated_total_time - elapsed_time
            progress_text.write(f"📊 Processing item {idx + 1} of {total_items} (Est. {int(remaining_time//3600)}h {int((remaining_time%3600)//60)}m {int(remaining_time%60)}s remaining)")
            progress_bar.progress((idx + 1) / total_items)
            
            
async def main():
    app = PromoApp()
    app.render_upload_section()
    await app.render_action_buttons()
    app.render_results_section()

if __name__ == "__main__":
    asyncio.run(main())
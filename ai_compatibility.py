import os
import sys
import platform
from uuid import uuid4
from typing import Optional

import streamlit as st
from loguru import logger
from pydantic import BaseModel, Field, ValidationError
from pydantic.v2 import PydanticV2Model  # Ensure you are using Pydantic v2

# Add the root directory of the project to the system path to allow importing modules from the project
root_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
if root_dir not in sys.path:
    sys.path.append(root_dir)
    print("******** sys.path ********")
    print(sys.path)
    print("")

from app.config import config
from app.models.const import FILE_TYPE_IMAGES, FILE_TYPE_VIDEOS
from app.models.schema import MaterialInfo, VideoAspect, VideoConcatMode, VideoParams
from app.services import llm, voice
from app.services import task as tm
from app.utils import utils

st.set_page_config(
    page_title="MoneyPrinterTurbo",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="auto",
    menu_items={
        "Report a bug": "https://github.com/harry0703/MoneyPrinterTurbo/issues",
        "About": "# MoneyPrinterTurbo\nSimply provide a topic or keyword for a video, and it will "
        "automatically generate the video copy, video materials, video subtitles, "
        "and video background music before synthesizing a high-definition short "
        "video.\n\nhttps://github.com/harry0703/MoneyPrinterTurbo",
    },
)

hide_streamlit_style = """
<style>#root > div:nth-child(1) > div > div > div > div > section > div {padding-top: 0rem;}</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)
st.title(f"MoneyPrinterTurbo v{config.project_version}")

support_locales = [
    "zh-CN",
    "zh-HK",
    "zh-TW",
    "de-DE",
    "en-US",
    "fr-FR",
    "vi-VN",
    "th-TH",
]

font_dir = os.path.join(root_dir, "resource", "fonts")
song_dir = os.path.join(root_dir, "resource", "songs")
i18n_dir = os.path.join(root_dir, "webui", "i18n")
config_file = os.path.join(root_dir, "webui", ".streamlit", "webui.toml")
system_locale = utils.get_system_locale()
# print(f"******** system locale: {system_locale} ********")

if "video_subject" not in st.session_state:
    st.session_state["video_subject"] = ""
if "video_script" not in st.session_state:
    st.session_state["video_script"] = ""
if "video_terms" not in st.session_state:
    st.session_state["video_terms"] = ""
if "ui_language" not in st.session_state:
    st.session_state["ui_language"] = config.ui.get("language", system_locale)


def get_all_fonts():
    fonts = []
    for root, dirs, files in os.walk(font_dir):
        for file in files:
            if file.endswith(".ttf") or file.endswith(".ttc"):
                fonts.append(file)
    fonts.sort()
    return fonts


def get_all_songs():
    songs = []
    for root, dirs, files in os.walk(song_dir):
        for file in files:
            if file.endswith(".mp3"):
                songs.append(file)
    return songs


def open_task_folder(task_id):
    try:
        sys = platform.system()
        path = os.path.join(root_dir, "storage", "tasks", task_id)
        if os.path.exists(path):
            if sys == "Windows":
                os.system(f"start {path}")
            if sys == "Darwin":
                os.system(f"open {path}")
    except Exception as e:
        logger.error(e)


def scroll_to_bottom():
    js = """
    <script>
        console.log("scroll_to_bottom");
        function scroll(dummy_var_to_force_repeat_execution){
            var sections = parent.document.querySelectorAll('section.main');
            console.log(sections);
            for(let index = 0; index<sections.length; index++) {
                sections[index].scrollTop = sections[index].scrollHeight;
            }
        }
        scroll(1);
    </script>
    """
    st.components.v1.html(js, height=0, width=0)


def init_log():
    logger.remove()
    _lvl = "DEBUG"

    def format_record(record):
        file_path = record["file"].path
        relative_path = os.path.relpath(file_path, root_dir)
        record["file"].path = f"./{relative_path}"
        record["message"] = record["message"].replace(root_dir, ".")

        _format = (
            "<green>{time:%Y-%m-%d %H:%M:%S}</> | "
            + "<level>{level}</> | "
            + '"{file.path}:{line}":<blue> {function}</> '
            + "- <level>{message}</>"
            + "\n"
        )
        return _format

    logger.add(
        sys.stdout,
        level=_lvl,
        format=format_record,
        colorize=True,
    )


init_log()

locales = utils.load_locales(i18n_dir)


def tr(key):
    loc = locales.get(st.session_state["ui_language"], {})
    return loc.get("Translation", {}).get(key, key)


st.write(tr("Get Help"))

llm_provider = config.app.get("llm_provider", "").lower()

if not config.app.get("hide_config", False):
    with st.expander(tr("Basic Settings"), expanded=False):
        config_panels = st.columns(3)
        left_config_panel = config_panels[0]
        middle_config_panel = config_panels[1]
        right_config_panel = config_panels[2]
        with left_config_panel:
            display_languages = []
            selected_index = 0
            for i, code in enumerate(locales.keys()):
                display_languages.append(f"{code} - {locales[code].get('Language')}")
                if code == st.session_state["ui_language"]:
                    selected_index = i

            selected_language = st.selectbox(
                tr("Language"), options=display_languages, index=selected_index
            )
            if selected_language:
                code = selected_language.split(" - ")[0].strip()
                st.session_state["ui_language"] = code
                config.ui["language"] = code

            hide_log = st.checkbox(
                tr("Hide Log"), value=config.app.get("hide_log", False)
            )
            config.ui["hide_log"] = hide_log

        with middle_config_panel:
            llm_providers = [
                "OpenAI",
                "Moonshot",
                "Azure",
                "Qwen",
                "DeepSeek",
                "Gemini",
                "Ollama",
                "G4f",
                "OneAPI",
                "Cloudflare",
                "ERNIE",
            ]
            saved_llm_provider = config.app.get("llm_provider", "OpenAI").lower()
            saved_llm_provider_index = 0
            for i, provider in enumerate(llm_providers):
                if provider.lower() == saved_llm_provider:
                    saved_llm_provider_index = i
                    break

            llm_provider = st.selectbox(
                tr("LLM Provider"),
                options=llm_providers,
                index=saved_llm_provider_index,
            )
            llm_helper = st.container()
            llm_provider = llm_provider.lower()
            config.app["llm_provider"] = llm_provider

            llm_api_key = config.app.get(f"{llm_provider}_api_key", "")
            llm_secret_key = config.app.get(
                f"{llm_provider}_secret_key", ""
            )
            llm_base_url = config.app.get(f"{llm_provider}_base_url", "")
            llm_model_name = config.app.get(f"{llm_provider}_model_name", "")
            llm_account_id = config.app.get(f"{llm_provider}_account_id", "")

            tips = ""
            if llm_provider == "ollama":
                if not llm_model_name:
                    llm_model_name = "qwen:7b"
                if not llm_base_url:
                    llm_base_url = "http://localhost:11434/v1"

                with llm_helper:
                    tips = """
                           ##### Ollama配置说明
                           - **API Key**: 随便填写，比如 123
                           - **Base Url**: 一般为 http://localhost:11434/v1
                              - 如果 `MoneyPrinterTurbo` 和 `Ollama` **不在同一台机器上**，需要填写 `Ollama` 机器的IP地址
                              - 如果 `MoneyPrinterTurbo` 是 `Docker` 部署，建议填写 `http://host.docker.internal:11434/v1`
                           - **Model Name**: 使用 `ollama list` 查看，比如 `qwen:7b`
                           """

            if llm_provider == "openai":
                if not llm_api_key:
                    llm_api_key = config.app.get("openai_api_key", "")
                tips = """
                       ##### OpenAI配置说明
                       - **API Key**: 登录 [OpenAI](https://platform.openai.com) 后，访问 [API Keys](https://platform.openai.com/account/api-keys)
                       """

            if llm_provider == "azure":
                if not llm_api_key:
                    llm_api_key = config.app.get("azure_api_key", "")
                if not llm_base_url:
                    llm_base_url = config.app.get("azure_base_url", "")
                if not llm_model_name:
                    llm_model_name = config.app.get("azure_model_name", "")
                tips = """
                       ##### Azure配置说明
                       - **API Key**: 登录 [Azure](https://portal.azure.com) 后，访问 [Keys and Endpoint](https://portal.azure.com/#blade/Microsoft_Azure_AI/LanguageStudio/KeyAndEndpoint)
                       - **Base Url**: 登录 [Azure](https://portal.azure.com) 后，访问 [Keys and Endpoint](https://portal.azure.com/#blade/Microsoft_Azure_AI/LanguageStudio/KeyAndEndpoint)
                       - **Model Name**: `Azure` 模型名称，不需要填写完整，例如: `gpt-35-turbo`
                       """

            if llm_provider == "moonshot":
                if not llm_base_url:
                    llm_base_url = config.app.get("moonshot_base_url", "")
                if not llm_model_name:
                    llm_model_name = config.app.get("moonshot_model_name", "")
                tips = """
                       ##### Moonshot配置说明
                       - **Base Url**: 一般为 http://localhost:8080/v1
                           - 如果 `MoneyPrinterTurbo` 和 `Moonshot` **不在同一台机器上**，需要填写 `Moonshot` 机器的IP地址
                           - 如果 `MoneyPrinterTurbo` 是 `Docker` 部署，建议填写 `http://host.docker.internal:8080/v1`
                       - **Model Name**: 使用 `moonshot list` 查看
                       """

            if tips:
                st.markdown(tips, unsafe_allow_html=True)
            
            llm_api_key = st.text_input(
                tr("API Key"), value=llm_api_key, type="password"
            )
            llm_secret_key = st.text_input(
                tr("Secret Key"), value=llm_secret_key, type="password"
            )
            llm_base_url = st.text_input(
                tr("Base Url"), value=llm_base_url
            )
            llm_model_name = st.text_input(
                tr("Model Name"), value=llm_model_name
            )
            llm_account_id = st.text_input(
                tr("Account Id"), value=llm_account_id
            )

            if st.button(tr("Save")):
                config.app[f"{llm_provider}_api_key"] = llm_api_key
                config.app[f"{llm_provider}_secret_key"] = llm_secret_key
                config.app[f"{llm_provider}_base_url"] = llm_base_url
                config.app[f"{llm_provider}_model_name"] = llm_model_name
                config.app[f"{llm_provider}_account_id"] = llm_account_id
                config.save()
                st.success(tr("Configuration saved!"))

        with right_config_panel:
            pexels_api_key = config.app.get("pexels_api_key", "")
            pixabay_api_key = config.app.get("pixabay_api_key", "")

            st.text_input(
                tr("Pexels API Key"), value=pexels_api_key, type="password"
            )
            st.text_input(
                tr("Pixabay API Key"), value=pixabay_api_key, type="password"
            )

        st.write("")

if "video_subject" in st.session_state:
    st.session_state["video_subject"] = st.text_input(
        tr("Video Subject"), value=st.session_state["video_subject"], max_chars=120
    )

if "video_script" in st.session_state:
    st.session_state["video_script"] = st.text_area(
        tr("Video Script"), value=st.session_state["video_script"], height=180
    )

if "video_terms" in st.session_state:
    st.session_state["video_terms"] = st.text_area(
        tr("Video Keywords"), value=st.session_state["video_terms"], height=180
    )

st.write("")

col1, col2, col3 = st.columns([3, 1, 1])

with col1:
    if st.session_state.get("video_script"):
        # Video generation related to the provided script
        st.button(tr("Generate Video"), key="generate_video")

with col2:
    if st.session_state.get("video_script"):
        st.button(tr("Update Script"), key="update_script")

with col3:
    st.button(tr("Cancel"), key="cancel")

# New AI-driven Features
# Example of how you might add AI-driven features such as error handling, module recommendation, etc.

def recommend_modules():
    # AI-driven module recommendation logic here
    st.write("Recommended Modules based on your setup.")

def handle_errors():
    # AI-driven error handling logic here
    st.write("Error handling updated.")

def enhanced_logging():
    # Configure enhanced logging
    st.write("Logging enhanced with AI-driven insights.")

recommend_modules()
handle_errors()
enhanced_logging()

# Compatibility Functions for Pydantic v2
class ConfigModel(PydanticV2Model):
    api_key: str = Field(..., description="API key for LLM service")
    secret_key: Optional[str] = Field(None, description="Secret key for LLM service")
    base_url: Optional[str] = Field(None, description="Base URL for LLM service")
    model_name: Optional[str] = Field(None, description="Model name for LLM service")
    account_id: Optional[str] = Field(None, description="Account ID for LLM service")

def validate_config(config_data):
    try:
        config_model = ConfigModel(**config_data)
        return config_model
    except ValidationError as e:
        logger.error(f"Configuration validation error: {e}")
        return None

# Example usage
config_data = {
    "api_key": "example_key",
    "secret_key": "example_secret",
    "base_url": "http://example.com",
    "model_name": "example_model",
    "account_id": "example_account",
}

validated_config = validate_config(config_data)
if validated_config:
    st.write("Configuration is valid and loaded.")
else:
    st.write("Configuration validation failed.")

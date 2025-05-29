import streamlit as st
import logging
from datetime import datetime
import os
import threading

import tableau_migration
from tableau_migration import (
    MigrationManifestSerializer,
    MigrationManifest,
    IUser
)

# ----------------------------
# Setup Logging
# ----------------------------
log_filename = f"migration_log_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
logging.basicConfig(
    filename=log_filename,
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
serializer = MigrationManifestSerializer()

# ----------------------------
# Streamlit UI Setup
# ----------------------------
st.title("Tableau Migration SDK - All-in-One App")

if 'migration_running' not in st.session_state:
    st.session_state.migration_running = False

log_area = st.empty()

# ----------------------------
# Input Configuration (UI)
# ----------------------------
with st.sidebar:
    st.header("🔐 Source Settings")
    src_url = st.text_input("Source Server URL")
    src_site = st.text_input("Source Site Content URL")
    src_token_name = st.text_input("Source Access Token Name")
    src_token = st.text_input("Source Access Token", type="password")
    src_sim = st.checkbox("Simulate Source API", False)

    st.header("🌐 Destination Settings")
    dst_url = st.text_input("Destination Pod URL")
    dst_site = st.text_input("Destination Site Content URL")
    dst_token_name = st.text_input("Destination Access Token Name")
    dst_token = st.text_input("Destination Access Token", type="password")
    dst_sim = st.checkbox("Simulate Destination API", False)

    st.header("👤 User Settings")
    email_domain = st.text_input("User Email Domain", "example.com")

    st.header("🧾 Manifest")
    use_manifest = st.radio("Use previous manifest if available?", ("Yes", "No"))
    manifest_path = st.text_input("Manifest File Path", "manifest.json")

# ----------------------------
# Load Manifest
# ----------------------------
def load_manifest(manifest_path: str):
    try:
        manifest = serializer.load(manifest_path)
        if manifest and use_manifest == 'Yes':
            return manifest
    except Exception as e:
        logger.warning(f"Manifest load failed: {e}")
    return None

# ----------------------------
# Custom Filter
# ----------------------------
def py_skip_local_user(user: IUser) -> bool:
    return not user.email.endswith(f"@{email_domain}")

# ----------------------------
# Display Results
# ----------------------------
def print_result(results):
    st.subheader("Migration Results")
    st.write(f"Successes: {len(results.successes)}")
    st.write(f"Failures: {len(results.failures)}")
    for failure in results.failures:
        st.error(f"Failure: {failure.message}")

# ----------------------------
# Migration Logic
# ----------------------------
def migrate():
    st.session_state.migration_running = True
    log_area.empty()
    try:
        logger.info("Migration started")

        builder = tableau_migration.MigrationPlanBuilder()
        migration = tableau_migration.Migrator()

        builder = builder \
            .from_source_tableau_server(
                server_url=src_url,
                site_content_url=src_site,
                access_token_name=src_token_name,
                access_token=src_token,
                create_api_simulator=src_sim) \
            .to_destination_tableau_cloud(
                pod_url=dst_url,
                site_content_url=dst_site,
                access_token_name=dst_token_name,
                access_token=dst_token,
                create_api_simulator=dst_sim) \
            .for_server_to_cloud() \
            .with_tableau_id_authentication_type() \
            .with_tableau_cloud_usernames(email_domain)

        # Add filter inline
        builder.filters.add(IUser, py_skip_local_user)

        prev_manifest = load_manifest(manifest_path)

        validation_result = builder.validate()
        if not validation_result.success:
            logger.error(f"Validation failed: {validation_result.Errors}")
            st.error(f"Validation failed: {validation_result.Errors}")
            return

        st.success("Migration plan validated.")
        logger.info("Validation passed.")

        plan = builder.build()
        results = migration.execute(plan, prev_manifest)
        serializer.save(results.manifest, manifest_path)

        print_result(results)
        st.success("Migration completed successfully.")
        logger.info("Migration finished successfully.")

    except Exception as e:
        st.error(f"Migration failed: {e}")
        logger.exception("Migration failed")
    finally:
        st.session_state.migration_running = False

# ----------------------------
# Start Button
# ----------------------------
if st.button("🚀 Start Migration", disabled=st.session_state.migration_running):
    threading.Thread(target=migrate, daemon=True).start()

if st.session_state.migration_running:
    st.info("Migration is running...")

st.caption(f"📁 Logs saved to: {log_filename}")

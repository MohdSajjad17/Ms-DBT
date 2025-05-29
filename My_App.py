import streamlit as st
import logging
from datetime import datetime
import configparser
import os
import threading

from dotenv import load_dotenv
load_dotenv()

import tableau_migration
from tableau_migration import (
    MigrationManifestSerializer,
    MigrationManifest,
    IUser
)

from print_result import print_result
from Hooks.Filters.user_filters import PySkipLocalUser

# Setup logging to Streamlit
log_dir = "migration/migration_logs"
os.makedirs(log_dir, exist_ok=True)
log_filename = os.path.join(log_dir, f"migration_log_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log")

logging.basicConfig(
    filename=log_filename,
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
serializer = MigrationManifestSerializer()

# Streamlit UI setup
st.title("Tableau Migration SDK Streamlit App")

if 'migration_running' not in st.session_state:
    st.session_state.migration_running = False

log_area = st.empty()  # placeholder for logs

def load_manifest(manifest_path: str) -> MigrationManifest | None:
    manifest = serializer.load(manifest_path)
    if manifest is not None:
        use_manifest = st.session_state.get('use_manifest', None)
        if use_manifest is None:
            use_manifest = st.sidebar.radio(
                f'Existing Manifest found at {manifest_path}. Use it?', ('Yes', 'No')
            )
            st.session_state.use_manifest = use_manifest
        if use_manifest == 'No':
            return None
        else:
            return manifest
    return None

def migrate():
    st.session_state.migration_running = True
    log_area.empty()

    try:
        current_file_path = os.path.abspath(__file__)
        manifest_path = os.path.join(os.path.dirname(current_file_path), 'manifest.json')

        plan_builder = tableau_migration.MigrationPlanBuilder()
        migration = tableau_migration.Migrator()

        config = configparser.ConfigParser()
        config.read('migration/config.ini')

        logger.debug(f"Loaded config sections: {config.sections()}")
        st.write(f"Loaded config sections: {config.sections()}")

        plan_builder = plan_builder \
            .from_source_tableau_server(
                server_url=config['SOURCE']['URL'],
                site_content_url=config['SOURCE']['SITE_CONTENT_URL'],
                access_token_name=config['SOURCE']['ACCESS_TOKEN_NAME'],
                access_token=os.environ.get('TABLEAU_MIGRATION_SOURCE_TOKEN', config['SOURCE']['ACCESS_TOKEN']),
                create_api_simulator=os.environ.get('TABLEAU_MIGRATION_SOURCE_SIMULATION', 'False') == 'True') \
            .to_destination_tableau_cloud(
                pod_url=config['DESTINATION']['URL'],
                site_content_url=config['DESTINATION']['SITE_CONTENT_URL'],
                access_token_name=config['DESTINATION']['ACCESS_TOKEN_NAME'],
                access_token=os.environ.get('TABLEAU_MIGRATION_DESTINATION_TOKEN', config['DESTINATION']['ACCESS_TOKEN']),
                create_api_simulator=os.environ.get('TABLEAU_MIGRATION_DESTINATION_SIMULATION', 'False') == 'True') \
            .for_server_to_cloud() \
            .with_tableau_id_authentication_type() \
            .with_tableau_cloud_usernames(config['USERS']['EMAIL_DOMAIN'])

        logger.info("Migration plan built successfully.")
        st.write("Migration plan built successfully.")

        # Add filter
        plan_builder.filters.add(IUser, PySkipLocalUser)

        prev_manifest = load_manifest(manifest_path)

        validation_result = plan_builder.validate()
        if not validation_result.success:
            logger.error(f"Migration plan validation failed: {validation_result.Errors}")
            st.error(f"Migration plan validation failed: {validation_result.Errors}")
            st.session_state.migration_running = False
            return

        st.write("Migration plan validated and built.")
        logger.info("Migration plan validated and built.")

        plan = plan_builder.build()
        results = migration.execute(plan, prev_manifest)
        serializer.save(results.manifest, manifest_path)

        print_result(results)
        st.success("Migration completed successfully.")
        logger.info("Migration completed successfully.")

    except Exception as e:
        st.error(f"Migration failed: {e}")
        logger.error(f"Migration failed: {e}")

    finally:
        st.session_state.migration_running = False

# Start button
if st.button("Start Migration", disabled=st.session_state.migration_running):
    threading.Thread(target=migrate, daemon=True).start()

if st.session_state.migration_running:
    st.info("Migration is running... Please wait.")

st.write(f"Logs are saved to: {log_filename}")

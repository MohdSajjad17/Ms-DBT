import streamlit as st
import threading
import tableau_migration
from tableau_migration import IUser

# --- Title ---
st.title("🔁 Simple Tableau Migration")

# --- Session State ---
if 'migration_running' not in st.session_state:
    st.session_state.migration_running = False

# --- Credentials UI ---
st.subheader("🔐 Source Tableau Server")
src_url = st.text_input("Source URL", placeholder="https://source-tableau.com")
src_site = st.text_input("Source Site Content URL", placeholder="site-id")
src_token_name = st.text_input("Source Token Name")
src_token = st.text_input("Source Token or Password", type="password")

st.subheader("📤 Destination Tableau Cloud")
dst_url = st.text_input("Destination URL", placeholder="https://us-east-1a.online.tableau.com")
dst_site = st.text_input("Destination Site Content URL", placeholder="site-id")
dst_token_name = st.text_input("Destination Token Name")
dst_token = st.text_input("Destination Token or Password", type="password")

email_domain = st.text_input("User Email Domain", value="example.com")

# --- Migration Function ---
def migrate():
    st.session_state.migration_running = True
    try:
        st.write("🔄 Starting migration...")

        builder = tableau_migration.MigrationPlanBuilder()
        migrator = tableau_migration.Migrator()

        builder = builder \
            .from_source_tableau_server(
                server_url=src_url,
                site_content_url=src_site,
                access_token_name=src_token_name,
                access_token=src_token,
                create_api_simulator=False) \
            .to_destination_tableau_cloud(
                pod_url=dst_url,
                site_content_url=dst_site,
                access_token_name=dst_token_name,
                access_token=dst_token,
                create_api_simulator=False) \
            .for_server_to_cloud() \
            .with_tableau_id_authentication_type() \
            .with_tableau_cloud_usernames(email_domain)

        validation_result = builder.validate()
        if not validation_result.success:
            st.error("❌ Validation failed:")
            st.error(validation_result.Errors)
            return

        plan = builder.build()
        results = migrator.execute(plan)

        # Output results
        st.success("✅ Migration Completed")
        st.write(f"✔️ Successes: {len(results.successes)}")
        st.write(f"❌ Failures: {len(results.failures)}")
        for failure in results.failures:
            st.error(f"Failure: {failure.message}")

    except Exception as e:
        st.error(f"❌ Migration failed: {e}")
    finally:
        st.session_state.migration_running = False

# --- Start Button ---
if st.button("🚀 Start Migration", disabled=st.session_state.migration_running):
    threading.Thread(target=migrate, daemon=True).start()

if st.session_state.migration_running:
    st.info("Migration is running... Please wait.")

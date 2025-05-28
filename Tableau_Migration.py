import streamlit as st
import tableauserverclient as TSC
import os
import re

st.set_page_config(page_title="Tableau Migration Tool", layout="wide")
st.markdown("<h1 style='text-align: center; color: #4B8BBE;'>🔁 Welcome to Migration World</h1>", unsafe_allow_html=True)
st.markdown("""
    <style>
    .footer { text-align: center; margin-top: 40px; color: #888; font-size: 16px; }
    </style>
    <div class="footer">Developed by <strong>Mohd Sajjad</strong></div>
""", unsafe_allow_html=True)

def sanitize(name):
    return re.sub(r'[^\w\-_\. ]', '_', name)

def create_local_dirs(project_name):
    base = os.path.join(os.getcwd(), "tableau_migration")
    src = os.path.join(base, "source", sanitize(project_name))
    dest = os.path.join(base, "destination", sanitize(project_name))
    os.makedirs(src, exist_ok=True)
    os.makedirs(dest, exist_ok=True)
    return src, dest

def get_local_path(type_: str, project_name: str, content_name: str, ext=".twbx") -> str:
    path = os.path.join(os.getcwd(), "tableau_migration", type_, sanitize(project_name))
    return os.path.join(path, f"{sanitize(content_name)}{ext}")

def get_auth(method, token_name, token_value, username, password, site):
    if method == "PAT":
        return TSC.PersonalAccessTokenAuth(token_name, token_value, site_id=site)
    else:
        return TSC.TableauAuth(username, password, site_id=site)

def get_server(url):
    return TSC.Server(url, use_server_version=True)

def migrate_permissions(src_server, src_item, dest_server, dest_item, item_type="workbook"):
    try:
        # Populate permissions depending on item type
        if item_type == "workbook":
            src_server.workbooks.populate_permissions(src_item)
            dest_server.workbooks.populate_permissions(dest_item)
            dest_perms_obj = dest_server.workbooks
        elif item_type == "datasource":
            src_server.datasources.populate_permissions(src_item)
            dest_server.datasources.populate_permissions(dest_item)
            dest_perms_obj = dest_server.datasources
        elif item_type == "flow":
            src_server.flows.populate_permissions(src_item)
            dest_server.flows.populate_permissions(dest_item)
            dest_perms_obj = dest_server.flows
        else:
            st.warning(f"⚠️ Permissions migration not implemented for type: {item_type}")
            return

        src_perms = src_item.permissions
        dest_perms = dest_item.permissions

        # Clear existing destination permissions
        for perm in dest_perms:
            dest_perms_obj._permissions.delete(dest_item, perm)

        src_users, _ = src_server.users.get()
        src_groups, _ = src_server.groups.get()
        dest_users, _ = dest_server.users.get()
        dest_groups, _ = dest_server.groups.get()

        src_user_map = {u.id: u for u in src_users}
        src_group_map = {g.id: g for g in src_groups}
        dest_user_map = {u.name: u for u in dest_users}
        dest_group_map = {g.name: g for g in dest_groups}

        missing_grantees = []

        for perm in src_perms:
            grantee_ref = perm.grantee
            dest_grantee = None

            if grantee_ref.tag_name == 'user':
                src_user = src_user_map.get(grantee_ref.id)
                if src_user and src_user.name in dest_user_map:
                    dest_grantee = dest_user_map[src_user.name]
                else:
                    missing_grantees.append(src_user.name if src_user else grantee_ref.id)

            elif grantee_ref.tag_name == 'group':
                src_group = src_group_map.get(grantee_ref.id)
                if src_group and src_group.name in dest_group_map:
                    dest_grantee = dest_group_map[src_group.name]
                else:
                    missing_grantees.append(src_group.name if src_group else grantee_ref.id)

            if dest_grantee:
                new_perm = TSC.PermissionsRule(grantee=dest_grantee, capabilities=perm.capabilities)
                dest_perms_obj.update_permissions(dest_item, [new_perm])
            else:
                st.warning(f"⚠️ Skipped permission for unknown grantee with ID: {grantee_ref.id}")

        if missing_grantees:
            st.info("ℹ️ Skipped the following missing users/groups:")
            st.write(list(set(missing_grantees)))

        st.success(f"🔑 Permissions migrated for {item_type}: {src_item.name}")

    except Exception as e:
        st.error(f"❌ Failed to migrate permissions for {item_type} {src_item.name}: {e}")

def download_workbooks(server, project_id, project_name):
    workbooks, _ = server.workbooks.get()
    selected = [wb for wb in workbooks if wb.project_id == project_id]
    files = []
    for wb in selected:
        path = get_local_path("source", project_name, wb.name, ext=".twbx")
        st.info(f"⬇️ Downloading workbook: {wb.name}")
        try:
            file_path = server.workbooks.download(wb.id, filepath=path)
            if os.path.exists(file_path):
                files.append((wb, file_path))
                st.success(f"✅ Downloaded workbook: {wb.name}")
            else:
                st.error(f"❌ File not saved correctly: {wb.name}")
        except Exception as e:
            st.error(f"❌ Download failed for workbook {wb.name}: {e}")
    return files

def publish_workbooks(src_server, dest_server, files_and_wbs, dest_project_id, project_name):
    for wb, path in files_and_wbs:
        st.info(f"⬆️ Publishing workbook: {wb.name}")
        try:
            new_wb = TSC.WorkbookItem(name=wb.name, project_id=dest_project_id)
            published_wb = dest_server.workbooks.publish(new_wb, path, mode=TSC.Server.PublishMode.Overwrite)
            st.success(f"✅ Published workbook: {wb.name}")
            migrate_permissions(src_server, wb, dest_server, published_wb, item_type="workbook")
        except Exception as e:
            st.error(f"❌ Failed to publish workbook {wb.name}: {e}")

def download_datasources(server, project_id, project_name):
    datasources, _ = server.datasources.get()
    selected = [ds for ds in datasources if ds.project_id == project_id]
    files = []
    for ds in selected:
        path = get_local_path("source", project_name, ds.name, ext=".tdsx")
        st.info(f"⬇️ Downloading datasource: {ds.name}")
        try:
            file_path = server.datasources.download(ds.id, filepath=path)
            if os.path.exists(file_path):
                files.append((ds, file_path))
                st.success(f"✅ Downloaded datasource: {ds.name}")
            else:
                st.error(f"❌ File not saved correctly: {ds.name}")
        except Exception as e:
            st.error(f"❌ Download failed for datasource {ds.name}: {e}")
    return files

def publish_datasources(dest_server, files_and_ds, dest_project_id):
    for ds, path in files_and_ds:
        st.info(f"⬆️ Publishing datasource: {ds.name}")
        try:
            new_ds = TSC.DatasourceItem(project_id=dest_project_id, name=ds.name)
            published_ds = dest_server.datasources.publish(new_ds, path, mode=TSC.Server.PublishMode.Overwrite)
            st.success(f"✅ Published datasource: {ds.name}")
            migrate_permissions(None, None, dest_server, published_ds, item_type="datasource")  # Src permissions unlikely for datasources, adjust if needed
        except Exception as e:
            st.error(f"❌ Failed to publish datasource {ds.name}: {e}")

def download_flows(server, project_id, project_name):
    flows, _ = server.flows.get()
    selected = [flow for flow in flows if flow.project_id == project_id]
    files = []
    for flow in selected:
        path = get_local_path("source", project_name, flow.name, ext=".tfl")
        st.info(f"⬇️ Downloading flow: {flow.name}")
        try:
            file_path = server.flows.download(flow.id, filepath=path)
            if os.path.exists(file_path):
                files.append((flow, file_path))
                st.success(f"✅ Downloaded flow: {flow.name}")
            else:
                st.error(f"❌ File not saved correctly: {flow.name}")
        except Exception as e:
            st.error(f"❌ Download failed for flow {flow.name}: {e}")
    return files

def publish_flows(dest_server, files_and_flows, dest_project_id):
    for flow, path in files_and_flows:
        st.info(f"⬆️ Publishing flow: {flow.name}")
        try:
            new_flow = TSC.FlowItem(project_id=dest_project_id, name=flow.name)
            published_flow = dest_server.flows.publish(new_flow, path, mode=TSC.Server.PublishMode.Overwrite)
            st.success(f"✅ Published flow: {flow.name}")
            migrate_permissions(None, None, dest_server, published_flow, item_type="flow")  # Src permissions unlikely for flows, adjust if needed
        except Exception as e:
            st.error(f"❌ Failed to publish flow {flow.name}: {e}")

def get_or_create_project(server, project_name):
    projects, _ = server.projects.get()
    project = next((p for p in projects if p.name == project_name), None)
    if project:
        return project
    else:
        new_project = TSC.ProjectItem(name=project_name)
        created_project = server.projects.create(new_project)
        st.info(f"📁 Created destination project: {project_name}")
        return created_project

# ----------------------------
# Streamlit UI Form
# ----------------------------
with st.form("migration_form"):
    st.subheader("🔐 Source Tableau")
    src_url = st.text_input("Source Server URL")
    src_site = st.text_input("Source Site Content URL (leave blank for default site)")
    src_auth_method = st.selectbox("Source Auth Method", ["PAT", "Username & Password"], key="src_auth")
    if src_auth_method == "PAT":
        src_token_name = st.text_input("Source PAT Name")
        src_token_secret = st.text_input("Source PAT Secret", type="password")
        src_username = src_password = None
    else:
        src_username = st.text_input("Source Username")
        src_password = st.text_input("Source Password", type="password")
        src_token_name = src_token_secret = None

    st.subheader("🔐 Destination Tableau")
    dest_url = st.text_input("Destination Server URL")
    dest_site = st.text_input("Destination Site Content URL (leave blank for default site)")
    dest_auth_method = st.selectbox("Destination Auth Method", ["PAT", "Username & Password"], key="dest_auth")
    if dest_auth_method == "PAT":
        dest_token_name = st.text_input("Destination PAT Name")
        dest_token_secret = st.text_input("Destination PAT Secret", type="password")
        dest_username = dest_password = None
    else:
        dest_username = st.text_input("Destination Username")
        dest_password = st.text_input("Destination Password", type="password")
        dest_token_name = dest_token_secret = None

    st.subheader("📁 Project Mapping")
    source_proj = st.text_input("Source Project Name")
    dest_proj = st.text_input("Destination Project Name")

    st.subheader("📦 Content Types to Migrate")
    content_types = st.multiselect(
        "Select content types to migrate",
        ["Workbooks", "Datasources", "Flows"],
        default=["Workbooks"]
    )

    submitted = st.form_submit_button("🚀 Start Migration")

# ----------------------------
# Migration Logic
# ----------------------------
if submitted:
    try:
        src_dir, dest_dir = create_local_dirs(source_proj)
        st.success(f"📂 Local folders created:\n- {src_dir}\n- {dest_dir}")

        src_auth = get_auth(src_auth_method, src_token_name, src_token_secret, src_username, src_password, src_site)
        src_server = get_server(src_url)
        src_server.auth.sign_in(src_auth)

        src_proj_obj = next((p for p in src_server.projects.get()[0] if p.name == source_proj), None)
        if not src_proj_obj:
            st.error(f"❌ Source project '{source_proj}' not found.")
            src_server.auth.sign_out()
            st.stop()

        # Download selected content types
        workbooks_files = download_workbooks(src_server, src_proj_obj.id, source_proj) if "Workbooks" in content_types else []
        datasources_files = download_datasources(src_server, src_proj_obj.id, source_proj) if "Datasources" in content_types else []
        flows_files = download_flows(src_server, src_proj_obj.id, source_proj) if "Flows" in content_types else []

        if not any([workbooks_files, datasources_files, flows_files]):
            st.warning("⚠️ No content downloaded.")
            src_server.auth.sign_out()
            st.stop()

        dest_auth = get_auth(dest_auth_method, dest_token_name, dest_token_secret, dest_username, dest_password, dest_site)
        dest_server = get_server(dest_url)
        dest_server.auth.sign_in(dest_auth)

        # Create destination project if not present
        dest_proj_obj = get_or_create_project(dest_server, dest_proj)

        # Publish selected content types
        if workbooks_files:
            publish_workbooks(src_server, dest_server, workbooks_files, dest_proj_obj.id, dest_proj)
        if datasources_files:
            publish_datasources(dest_server, datasources_files, dest_proj_obj.id)
        if flows_files:
            publish_flows(dest_server, flows_files, dest_proj_obj.id)

        src_server.auth.sign_out()
        dest_server.auth.sign_out()

        st.success("🎉 Migration completed successfully!")

    except Exception as e:
        st.error(f"❌ Migration failed: {e}")

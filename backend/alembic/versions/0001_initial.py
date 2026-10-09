"""CineAI B1 initial PostgreSQL schema, frozen at revision 0001."""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE TABLE project (\n\tid VARCHAR(36) NOT NULL, \n\towner_id VARCHAR NOT NULL, \n\tname VARCHAR(100) NOT NULL, \n\tdescription VARCHAR NOT NULL, \n\tstyle VARCHAR NOT NULL, \n\tratio VARCHAR NOT NULL, \n\tstatus VARCHAR NOT NULL, \n\tcover_key VARCHAR, \n\toutline JSONB, \n\texport_settings JSONB, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id)\n)"
    )
    op.execute(
        "CREATE TABLE storage_cleanup (\n\tid VARCHAR(36) NOT NULL, \n\tkeys JSONB NOT NULL, \n\tPRIMARY KEY (id)\n)"
    )
    op.execute(
        "CREATE TABLE asset (\n\tid VARCHAR(36) NOT NULL, \n\tproject_id VARCHAR(36) NOT NULL, \n\tkind VARCHAR NOT NULL, \n\tobject_key VARCHAR NOT NULL, \n\tcontent_type VARCHAR NOT NULL, \n\tsize_bytes INTEGER NOT NULL, \n\tduration_ms INTEGER, \n\twidth INTEGER, \n\theight INTEGER, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(project_id) REFERENCES project (id) ON DELETE CASCADE, \n\tUNIQUE (object_key)\n)"
    )
    op.execute("CREATE INDEX ix_asset_project_id ON asset (project_id)")
    op.execute(
        "CREATE TABLE character (\n\tid VARCHAR(36) NOT NULL, \n\tproject_id VARCHAR(36) NOT NULL, \n\tname VARCHAR NOT NULL, \n\tage VARCHAR NOT NULL, \n\tdescription VARCHAR NOT NULL, \n\tclothing VARCHAR NOT NULL, \n\tvoice VARCHAR NOT NULL, \n\tvoice_id VARCHAR NOT NULL, \n\timage_key VARCHAR, \n\tconsistency VARCHAR NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(project_id) REFERENCES project (id) ON DELETE CASCADE\n)"
    )
    op.execute("CREATE INDEX ix_character_project_id ON character (project_id)")
    op.execute(
        "CREATE TABLE export_job (\n\tid VARCHAR(36) NOT NULL, \n\tproject_id VARCHAR(36) NOT NULL, \n\tstatus VARCHAR NOT NULL, \n\tprogress INTEGER NOT NULL, \n\tsettings JSONB NOT NULL, \n\toutput_key VARCHAR, \n\tcover_key VARCHAR, \n\tsubtitle_key VARCHAR, \n\tduration_sec FLOAT, \n\tcost_cents INTEGER NOT NULL, \n\terror VARCHAR, \n\tlogs JSONB NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tfinished_at TIMESTAMP WITH TIME ZONE, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(project_id) REFERENCES project (id) ON DELETE CASCADE\n)"
    )
    op.execute("CREATE INDEX ix_export_job_project_id ON export_job (project_id)")
    op.execute(
        "CREATE TABLE scene (\n\tid VARCHAR(36) NOT NULL, \n\tproject_id VARCHAR(36) NOT NULL, \n\torder_index INTEGER NOT NULL, \n\ttitle VARCHAR NOT NULL, \n\tshot_type VARCHAR NOT NULL, \n\tcamera_move VARCHAR NOT NULL, \n\tduration_sec FLOAT NOT NULL, \n\timage_prompt VARCHAR NOT NULL, \n\tvideo_prompt VARCHAR NOT NULL, \n\tdialogue VARCHAR NOT NULL, \n\tnarration VARCHAR NOT NULL, \n\tstatus VARCHAR NOT NULL, \n\tmodel VARCHAR NOT NULL, \n\tseed VARCHAR NOT NULL, \n\tdirector_data JSONB, \n\tfirst_frame_key VARCHAR, \n\tvideo_key VARCHAR, \n\taudio_key VARCHAR, \n\tnarration_key VARCHAR, \n\taudio_duration_ms INTEGER NOT NULL, \n\tlast_error VARCHAR, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_scene_order UNIQUE (project_id, order_index), \n\tFOREIGN KEY(project_id) REFERENCES project (id) ON DELETE CASCADE\n)"
    )
    op.execute("CREATE INDEX ix_scene_project_id ON scene (project_id)")
    op.execute(
        "CREATE TABLE task (\n\tid VARCHAR(36) NOT NULL, \n\tproject_id VARCHAR(36) NOT NULL, \n\tscene_id VARCHAR(36), \n\tkind VARCHAR NOT NULL, \n\tstatus VARCHAR NOT NULL, \n\tprogress INTEGER NOT NULL, \n\tprovider VARCHAR, \n\tprovider_task_id VARCHAR, \n\tdedupe_key VARCHAR NOT NULL, \n\tpayload JSONB NOT NULL, \n\tresult JSONB, \n\tlogs JSONB NOT NULL, \n\tattempts INTEGER NOT NULL, \n\tcost_cents INTEGER NOT NULL, \n\testimated_cost_cents INTEGER NOT NULL, \n\terror VARCHAR, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tstarted_at TIMESTAMP WITH TIME ZONE, \n\tfinished_at TIMESTAMP WITH TIME ZONE, \n\tdispatched_at TIMESTAMP WITH TIME ZONE, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(project_id) REFERENCES project (id) ON DELETE CASCADE, \n\tFOREIGN KEY(scene_id) REFERENCES scene (id) ON DELETE CASCADE\n)"
    )
    op.execute("CREATE INDEX ix_task_project_id ON task (project_id)")
    op.execute("CREATE INDEX ix_task_scene_id ON task (scene_id)")
    op.execute("CREATE INDEX ix_task_dedupe_key ON task (dedupe_key)")
    op.execute("CREATE INDEX ix_task_status ON task (status)")
    op.execute(
        "CREATE UNIQUE INDEX uq_active_scene_kind ON task (scene_id, kind) WHERE status IN ('queued','running')"
    )


def downgrade():
    op.drop_table("task")
    op.drop_table("scene")
    op.drop_table("export_job")
    op.drop_table("character")
    op.drop_table("asset")
    op.drop_table("storage_cleanup")
    op.drop_table("project")

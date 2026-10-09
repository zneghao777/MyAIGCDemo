"""Project-first scene locking shared by selection and worker write paths."""
from app.models import Project, Scene
from app.services.resources import ensure_idle, require


async def locked_scene(db, scene_id, *, check_idle=True):
    # Read only the owner before locking; neither cached object is used for writes.
    scene = await require(db, Scene, scene_id)
    project = await require(db, Project, scene.project_id, True)
    await db.refresh(project)
    scene = await require(db, Scene, scene_id, True)
    await db.refresh(scene)
    if check_idle:
        await ensure_idle(db, scene.project_id, scene.id)
    return project, scene

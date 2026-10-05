"""Fast, deterministic mesh-BVH motion checks in the uv environment.

OCC handles static solid interference. FCL handles thousands of transformed
triangle-mesh distance queries without retessellating/refusing a BREP per pose.
Containment checks supplement FCL's mesh surface queries.
"""
import gzip
import json
import math

import fcl
import numpy as np
import trimesh


def collision_object(mesh):
    model = fcl.BVHModel()
    model.beginModel(len(mesh.vertices), len(mesh.faces))
    model.addSubModel(np.asarray(mesh.vertices,dtype=np.float64), np.asarray(mesh.faces,dtype=np.int32))
    model.endModel()
    return fcl.CollisionObject(model)


def check_pair(body, moving, body_object, moving_object, transform, clearance):
    vertices = trimesh.transform_points(moving.vertices, transform)
    bb = np.array([vertices.min(0), vertices.max(0)])
    lower = np.linalg.norm(np.maximum(0,np.maximum(body.bounds[0]-bb[1],bb[0]-body.bounds[1])))
    if lower >= clearance:
        return {"status":"PASS", "distance_lower_bound_mm":round(float(lower),6), "method":"AABB lower bound"}
    moving_object.setTransform(fcl.Transform(transform[:3,:3],transform[:3,3]))
    distance = fcl.distance(body_object,moving_object,fcl.DistanceRequest(),fcl.DistanceResult())
    if distance <= 1e-6:
        return {"status":"CONTACT_OR_INTERFERENCE","distance_mm":0,"method":"FCL triangle BVH"}
    # A disjoint surface can still enclose another whole solid. Each ROM object
    # is connected (validated separately); test representative points both ways.
    inverse = np.linalg.inv(transform)
    contained = False
    if body.is_watertight and moving.is_watertight:
        direction=np.array([.439,.713,.547])
        inside=trimesh.ray.ray_util.contains_points
        contained = bool(inside(body.ray,vertices[:1],check_direction=direction)[0] or
                         inside(moving.ray,trimesh.transform_points(body.vertices[:1],inverse),check_direction=direction)[0])
    if contained:
        return {"status":"CONTAINMENT","distance_mm":0,"method":"FCL surfaces plus ray containment"}
    return {"status":"PASS" if distance>=clearance else "CLEARANCE", "distance_mm":round(float(distance),6),
            "required_clearance_mm":clearance,"method":"FCL triangle BVH plus containment"}


def run_motion(out, job, root):
    np.random.seed(0)
    scene_path=out/"scene.json.gz"
    scene=[r for r in json.loads(gzip.decompress(scene_path.read_bytes())) if r['kind']!='leg']
    by_id={r['id']:r for r in scene}
    assembly=json.loads((out/"assembly.json").read_text())
    bodies={p['id'].removeprefix('body.'):trimesh.load(out/p['files']['stl'],force='mesh') for p in assembly['parts']}
    body_objects={n:collision_object(m) for n,m in bodies.items()}
    rows,animation=[],[]
    # Mesh approximation tolerance is additional to the nominal clearance.
    clearance=job['params']['clearance_mm']+job['params']['checks']['mesh_deflection_mm']
    for leg in job['legs']:
        meshes={}
        for role in ['upper','lower']:
            r=leg[role]
            m=trimesh.load(root/r['source'],force='mesh')
            m.apply_transform(np.asarray(r['source_to_rest_matrix']).reshape(4,4))
            meshes[role]=m
            scene.append({'id':'leg.'+leg['name']+'.'+role,'kind':'leg','color':[.75,.19,.12],
                          'vertices':m.vertices.tolist(),'faces':m.faces.tolist()})
        for role,prefix in [('foot-servo','servo.'),('foot-horn','horn.')]:
            r=by_id[prefix+leg['name']+'.foot']
            meshes[role]=trimesh.Trimesh(vertices=r['vertices'],faces=r['faces'],process=True)
        objects={r:collision_object(m) for r,m in meshes.items()}
        for hip,foot,mode in leg['poses']:
            hip_transform=trimesh.transformations.rotation_matrix(math.radians(hip),leg['hip_axis'],leg['hip_center_mm'])
            foot_transform=trimesh.transformations.rotation_matrix(math.radians(foot),leg['foot_axis'],leg['foot_center_mm'])
            for role,mesh in meshes.items():
                transform=hip_transform@foot_transform if role in ['lower','foot-horn'] else hip_transform
                for name,body in bodies.items():
                    result=check_pair(body,mesh,body_objects[name],objects[role],transform,clearance)
                    rows.append({'leg':leg['name'],'link':role,'body':name,'hip_deg':hip,'foot_deg':foot,'mode':mode,**result})
            animation.append({'leg':leg['name'],'hip_deg':hip,'foot_deg':foot,'mode':mode})
        print('FCL ROM checked:',leg['name'],flush=True)
    scene_path.write_bytes(gzip.compress(json.dumps(scene,separators=(',',':')).encode(),mtime=0))
    (out/'rom-animation.json').write_text(json.dumps({'frames':animation,'kinematics':job['legs']},indent=2)+'\n')
    return rows

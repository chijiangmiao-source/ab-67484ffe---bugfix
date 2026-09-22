export interface AllocateRequest {
  scene_id: string;
  client_op_id: string;
  notes: string;
  inject_failure_after_commit?: boolean;
}

export interface Allocation {
  scene_id: string;
  client_op_id: string;
  notes: string;
  shot_number: number;
  replayed: boolean;
}

export interface ShotNumberItem {
  scene_id: string;
  client_op_id: string;
  notes: string;
  shot_number: number;
  created_at: string;
}

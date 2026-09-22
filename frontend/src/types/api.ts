
export interface LoginResponse {
    token: string
    user: { id: number; username: string }
}

export interface UserInfo {
    id: number
    username: string
    email?: string
    is_staff?: boolean
    phone?: string
    avatar?: string
}

export interface RegisterPayload {
    username: string
    password: string
    email?: string
    phone?: string
}

export interface ChangePasswordPayload {
    old_password: string
    new_password: string
    confirm_password: string
}

/** 任务阶段（后端只读嵌套数组，随任务详情一起返回） */
export interface TaskStage {
    id: number
    stage_type: string
    stage_type_display: string
    status: string
    status_display: string
    error_message: string
    input_data: Record<string, any>
    output_data: Record<string, any>
    created_at: string
    started_at: string | null
    completed_at: string | null
    retry_count: number
}

/** 异步任务 */
export interface Task {
    id: number
    device: number
    device_hostname: string
    task_type: string
    task_type_display: string
    status: string
    status_display: string
    params: Record<string, any>
    result: Record<string, any> | null
    error_message: string
    progress: number
    created_at: string
    started_at: string | null
    completed_at: string | null
    stages: TaskStage[]
}

/** DRF 分页响应 */
export interface Paginated<T> {
    count: number
    next: string | null
    previous: string | null
    results: T[]
}

/** 设备下拉选项（设备接口每项至少含 id / hostname） */
export interface DeviceOption {
    id: number
    hostname: string
}

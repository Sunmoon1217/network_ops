/** 侧边导航菜单项（递归结构） */
export interface MenuItem {
    index: string
    label: string
    icon?: () => any
    children?: MenuItem[]
}

/** 统计卡片视图模型：level 决定异常计数的配色 */
export interface StatCard {
    label: string
    value: number
    hint: string
    level: 'normal' | 'warning' | 'danger'
}

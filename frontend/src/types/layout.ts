export interface MenuItem {
    index: string
    label: string
    icon?: () => any
    children?: MenuItem[]
}
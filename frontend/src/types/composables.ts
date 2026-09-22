/** 列表页取数回调：返回一个 Promise 的请求函数 */
export type Fetcher = () => Promise<any>

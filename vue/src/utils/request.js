import { ElMessage } from 'element-plus'
import router from '../router'
import axios from "axios";
import { clearSession } from './session'
import { extractRequestErrorMessage } from './requestError'

const requestInstance = axios.create({
    baseURL: import.meta.env.VITE_BASE_URL,
    withCredentials: true,
    timeout: 30000  // 后台接口超时时间设置
})

export async function notifyRequestError(error, fallback = '请求失败，请稍后重试') {
    if (axios.isCancel(error) || error?.userNotified) return
    // Reserve this error before awaiting Blob.text(), so the interceptor and
    // local catch cannot display the same failure twice.
    if (error && typeof error === 'object') error.userNotified = true
    const message = await extractRequestErrorMessage(error, fallback)
    ElMessage.error(message)
}

// request 拦截器
// 可以自请求发送前对请求做一些处理
requestInstance.interceptors.request.use(config => {
    // Content-Type 交给 axios 按请求体类型自动设置（JSON 对象→json，FormData→multipart）
    return config
}, error => {
    return Promise.reject(error)
});

// response 拦截器
// 可以在接口响应后统一处理结果
requestInstance.interceptors.response.use(
    response => {
        let res = response.data;
        // 兼容服务端返回的字符串数据
        if (typeof res === 'string') {
            res = res ? JSON.parse(res) : res
        }
        return res;
    },
    error => {
        if (error.response?.status === 401) {
            clearSession()
            if (router.currentRoute.value.path !== '/login') {
                notifyRequestError(error, '登录状态已失效，请重新登录')
                router.push('/login')
            }
        } else if (axios.isCancel(error)) {
            return Promise.reject(error)
        } else if (!error.config?.skipErrorToast) {
            notifyRequestError(error)
        }
        return Promise.reject(error)
    }
)


/**
 * The response interceptor unwraps AxiosResponse to the API envelope or Blob.
 * Expose that runtime contract to JavaScript type checking.
 *
 * @typedef {import('axios').AxiosRequestConfig & { skipErrorToast?: boolean }} RequestOptions
 * @typedef {{
 *   get(url: string, options?: RequestOptions): Promise<any>,
 *   post(url: string, data?: any, options?: RequestOptions): Promise<any>,
 *   put(url: string, data?: any, options?: RequestOptions): Promise<any>,
 *   patch(url: string, data?: any, options?: RequestOptions): Promise<any>,
 *   delete(url: string, options?: RequestOptions): Promise<any>
 * }} ApiClient
 */
const request = /** @type {ApiClient} */ (requestInstance)

export default request

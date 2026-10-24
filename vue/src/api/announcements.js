import request from '@/utils/request'
import { apiPath } from './apiPaths.js'

export const listAnnouncements = (params = {}, options = {}) => request.get(
  apiPath('announcements.list'),
  { ...options, params },
)

export const markAnnouncementRead = (announcementId, options = {}) => request.put(
  apiPath('announcements.read', { announcement_id: announcementId }),
  null,
  options,
)

export const markAllAnnouncementsRead = (options = {}) => request.put(
  apiPath('announcements.read_all'),
  null,
  options,
)

export const listAdminAnnouncements = (params = {}, options = {}) => request.get(
  apiPath('announcements.admin_list'),
  { ...options, params },
)

export const createAnnouncement = (payload, options = {}) => request.post(
  apiPath('announcements.create'),
  payload,
  options,
)

export const updateAnnouncement = (announcementId, payload, options = {}) => request.put(
  apiPath('announcements.update', { announcement_id: announcementId }),
  payload,
  options,
)

export const updateAnnouncementStatus = (announcementId, status, options = {}) => request.patch(
  apiPath('announcements.status', { announcement_id: announcementId }),
  { status },
  options,
)

export const deleteAnnouncement = (announcementId, options = {}) => request.delete(
  apiPath('announcements.delete', { announcement_id: announcementId }),
  options,
)

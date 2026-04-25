/**
 * Comments System - Shared UI Component
 * Usage: initComments(targetType, targetId, containerSelector)
 */
(function () {
    'use strict';

    let _currentUser = null;

    async function getCurrentUser() {
        if (_currentUser !== null) return _currentUser;
        try {
            const res = await fetch('/auth/me');
            if (res.ok) {
                const data = await res.json();
                _currentUser = data.error ? null : data;
            } else {
                _currentUser = null;
            }
        } catch {
            _currentUser = null;
        }
        return _currentUser;
    }

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function timeAgo(val) {
        // val can be int timestamp or ISO string
        const ts = typeof val === 'number' ? val * 1000 : new Date(val).getTime();
        const now = Date.now();
        const diff = Math.floor((now - ts) / 1000);
        if (diff < 60) return '刚刚';
        if (diff < 3600) return Math.floor(diff / 60) + '分钟前';
        if (diff < 86400) return Math.floor(diff / 3600) + '小时前';
        if (diff < 2592000) return Math.floor(diff / 86400) + '天前';
        return new Date(ts).toLocaleDateString('zh-CN');
    }

    function renderComment(c, isReply) {
        const avatar = c.author_name ? c.author_name.charAt(0).toUpperCase() : '?';
        const statusBadge = c.status !== 'approved'
            ? `<span class="comment-status-badge badge-${c.status}">${c.status === 'pending' ? '待审核' : '已拒绝'}</span>`
            : '';

        // can_review comes from backend (true only for content author on pending comments)
        const canReview = c.can_review && c.status === 'pending';
        const reviewBtns = canReview
            ? `<div class="review-actions">
                   <button class="btn-approve" onclick="Comments.review(${c.id}, 'approved')">通过</button>
                   <button class="btn-reject" onclick="Comments.review(${c.id}, 'rejected')">拒绝</button>
               </div>`
            : '';

        const replyBtn = !isReply && c.status === 'approved'
            ? `<button onclick="Comments.toggleReply(${c.id})">回复</button>`
            : '';

        const deleteBtn = c.can_delete
            ? `<button onclick="Comments.remove(${c.id})">删除</button>`
            : '';

        const replies = (!isReply && c.replies && c.replies.length > 0)
            ? `<ul class="comment-replies">${c.replies.map(r => renderComment(r, true, canReview)).join('')}</ul>`
            : '';

        return `
        <li class="comment-item" data-id="${c.id}">
            <div class="comment-author-row">
                <span class="comment-avatar">${escapeHtml(avatar)}</span>
                <span class="comment-author">${escapeHtml(c.author_name || '匿名')}</span>
                <span class="comment-time">${timeAgo(c.created_at)}</span>
                ${statusBadge}
            </div>
            <div class="comment-body">${escapeHtml(c.content)}</div>
            <div class="comment-actions">
                ${replyBtn}${deleteBtn}
            </div>
            ${reviewBtns}
            <div class="reply-form-wrapper" id="reply-form-${c.id}">
                <textarea placeholder="写回复..." rows="2"></textarea>
                <div class="reply-actions">
                    <button class="btn-reply-submit" onclick="Comments.submitReply(${c.id})">回复</button>
                    <button class="btn-cancel" onclick="Comments.toggleReply(${c.id})">取消</button>
                </div>
            </div>
            ${replies}
        </li>`;
    }

    async function loadComments(targetType, targetId, container) {
        const listEl = container.querySelector('.comments-list');
        const countEl = container.querySelector('.comments-count');
        listEl.innerHTML = '<div class="comments-loading">加载中...</div>';

        try {
            const res = await fetch(`/api/comments?target_type=${targetType}&target_id=${targetId}`);
            const data = await res.json();

            if (data.error) {
                listEl.innerHTML = `<div class="comments-empty">${escapeHtml(data.error)}</div>`;
                return;
            }

            // Fetch pending comments for the logged-in user (own pending)
            let pendingComments = [];
            const user = await getCurrentUser();
            if (user) {
                try {
                    const pres = await fetch(`/api/comments/pending?target_type=${targetType}&target_id=${targetId}`);
                    if (pres.ok) {
                        const pdata = await pres.json();
                        if (!pdata.error && pdata.comments) {
                            pendingComments = pdata.comments;
                        }
                    }
                } catch { /* ignore */ }
            }

            const approved = data.comments || data;
            // can_review from backend: true if current user is content author
            const canReview = data.can_review || false;

            // Deduplicate: pending IDs might overlap with approved (own pending shown in both APIs)
            const seenIds = new Set();

            if (approved.length === 0 && pendingComments.length === 0) {
                listEl.innerHTML = '<div class="comments-empty"><div class="empty-icon">💬</div>暂无评论，来抢沙发吧</div>';
                if (countEl) countEl.textContent = '0 条评论';
                return;
            }

            const totalCount = approved.length + pendingComments.length;
            if (countEl) countEl.textContent = `${totalCount} 条评论`;

            let html = '';
            // Show pending first (some may already be in approved if they were reviewed before reload)
            const renderAndTrack = (c, ...args) => {
                if (seenIds.has(c.id)) return '';
                seenIds.add(c.id);
                return renderComment(c, ...args);
            };
            if (pendingComments.length > 0) {
                // Pending shown to comment author: can delete + can review (if content author)
                html += pendingComments.map(c => renderAndTrack({...c, can_delete: true}, false, canReview)).join('');
            }
            html += approved.map(c => renderAndTrack(c, false, canReview)).join('');
            listEl.innerHTML = html;

        } catch (e) {
            listEl.innerHTML = '<div class="comments-empty">加载失败，请刷新重试</div>';
        }
    }

    // Per-section submit lock to prevent double-submit
    const _submitting = new WeakMap();

    async function submitComment(targetType, targetId, container) {
        const user = await getCurrentUser();
        if (!user) {
            window.location.href = '/login';
            return;
        }

        const textarea = container.querySelector('.comment-form textarea');
        const content = textarea.value.trim();
        if (!content) return;

        // Prevent concurrent submits on the same section
        if (_submitting.get(container)) return;
        _submitting.set(container, true);

        const btn = container.querySelector('.btn-submit');
        const origText = btn.textContent;
        btn.disabled = true;
        btn.textContent = '提交中...';

        try {
            const res = await fetch('/api/comments', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    target_type: targetType,
                    target_id: targetId,
                    content: content
                })
            });

            const data = await res.json();
            if (data.error) {
                alert(data.error);
            } else {
                textarea.value = '';
                alert('评论已提交，等待审核');
                await loadComments(targetType, targetId, container);
            }
        } catch {
            alert('提交失败，请重试');
        } finally {
            btn.disabled = false;
            btn.textContent = origText;
            _submitting.set(container, false);
        }
    }

    function toggleReply(commentId) {
        const el = document.getElementById('reply-form-' + commentId);
        if (el) el.classList.toggle('active');
    }

    async function submitReply(parentId) {
        const user = await getCurrentUser();
        if (!user) {
            window.location.href = '/login';
            return;
        }

        const formEl = document.getElementById('reply-form-' + parentId);
        const textarea = formEl.querySelector('textarea');
        const content = textarea.value.trim();
        if (!content) return;

        // Find target info from the section
        const section = formEl.closest('.comments-section');
        const targetType = section.dataset.targetType;
        const targetId = section.dataset.targetId;

        try {
            const res = await fetch('/api/comments', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    target_type: targetType,
                    target_id: Number(targetId),
                    parent_id: parentId,
                    content: content
                })
            });

            const data = await res.json();
            if (data.error) {
                alert(data.error);
            } else {
                textarea.value = '';
                formEl.classList.remove('active');
                alert('回复已提交，等待审核');
                await loadComments(targetType, Number(targetId), section);
            }
        } catch {
            alert('回复失败，请重试');
        }
    }

    async function review(commentId, status) {
        try {
            const res = await fetch(`/api/comments/${commentId}/review`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: status === 'approved' ? 'approve' : 'reject' })
            });
            const data = await res.json();
            if (data.error) {
                alert(data.error);
            } else {
                const section = event && event.target
                    ? event.target.closest('.comments-section')
                    : document.querySelector(`.comments-section[data-target-type][data-target-id]`) || document.querySelector('.comments-section');
                if (section) {
                    await loadComments(section.dataset.targetType, Number(section.dataset.targetId), section);
                }
            }
        } catch {
            alert('操作失败');
        }
    }

    async function remove(commentId) {
        if (!confirm('确定删除这条评论吗？')) return;
        try {
            const res = await fetch(`/api/comments/${commentId}`, { method: 'DELETE' });
            const data = await res.json();
            if (data.error) {
                alert(data.error);
            } else {
                const section = event && event.target
                    ? event.target.closest('.comments-section')
                    : document.querySelector(`.comments-section[data-target-type][data-target-id]`) || document.querySelector('.comments-section');
                if (section) {
                    await loadComments(section.dataset.targetType, Number(section.dataset.targetId), section);
                }
            }
        } catch {
            alert('删除失败');
        }
    }

    // Init
    window.Comments = {
        init: async function (targetType, targetId, containerSelector) {
            const container = document.querySelector(containerSelector);
            if (!container) return;

            container.dataset.targetType = targetType;
            container.dataset.targetId = targetId;

            const user = await getCurrentUser();

            // Show form if logged in
            const formEl = container.querySelector('.comment-form');
            const hintEl = container.querySelector('.comment-login-hint');
            if (user) {
                if (formEl) formEl.style.display = 'block';
                if (hintEl) hintEl.style.display = 'none';
            } else {
                if (formEl) formEl.style.display = 'none';
                if (hintEl) hintEl.style.display = 'block';
            }

            await loadComments(targetType, targetId, container);
        },
        submit: function (targetType, targetId, containerSelector) {
            const container = document.querySelector(containerSelector);
            if (container) submitComment(targetType, targetId, container);
        },
        toggleReply,
        submitReply,
        review,
        remove
    };
})();

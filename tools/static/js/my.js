(function () {
    // submit form
    $('.filter').on('change', function () {
        $('#form').submit();
    });

    // sort by headers of table
    let _order_by = $('#order_by');
    let _desc = $('#desc');
    let src_order_by = _order_by.val();
    let src_desc = _desc.val();
    $('.sortable').each(function () {
        $(this).attr('title', '点击排序');
        let order_by = $(this).attr('id');
        if (order_by === src_order_by) {
            $(this).children('span.arrow').attr('class', 'arrow ' + src_desc);
            $(this).on('click', function () {
                _desc.val(src_desc.toLowerCase() === 'desc' ? 'asc' : 'desc');
                $('#form').submit();
            });
        } else {
            $(this).children('span.arrow').attr('class', 'arrow');
            $(this).on('click', function () {
                _order_by.val(order_by);
                _desc.val('asc');
                $('#form').submit();
            });
        }
    });

    // archive events
    $('.playBtn').each(function () {
        updateArchived($(this), $(this).data('archived'), $(this).data('id'));
    });

    // checkbox
    let selectedSpan = $('#selectedCount');
    $('#selectAll').on('click', function () {
        let checked = $(this).prop('checked');
        $('.batchSelect').prop('checked', checked);
        if (checked) {
            selectedSpan.text($('#totalCount').text());
        } else {
            selectedSpan.text(0);
        }
    });
    $('.batchSelect').on('click', function () {
        let checked = $(this).prop('checked');
        let selectCount = parseInt(selectedSpan.text());
        if (checked) {
            let all_checked = true;
            $('.batchSelect').each(function () {
                if (!$(this).prop('checked')) {
                    all_checked = false;
                }
            });
            $('#selectAll').prop('checked', all_checked);
            selectCount++;
        } else {
            $('#selectAll').prop('checked', false);
            selectCount--;
        }
        selectedSpan.text(selectCount);
    });
})();

function archiveAll() {
    $.getJSON('/video/archive_all', function (result) {
        if (result['success']) {
            alert(result['archived'] + ' archived, ' + result['unarchived'] + ' unarchived');
        }
    })
}

function bindClick(_this, tip, href, subject_id, confirmMsg) {
    let clickTip = _this.prev('.clickTip');
    _this.off('click').on('click', function () {
        if (!confirmMsg || confirm(confirmMsg)) {
            _this.attr('hidden', true);
            clickTip.text(tip);
            clickTip.attr('hidden', false);
            let spotCount = 0;
            let timer = setInterval(function () {
                let text = tip + '.';
                for (let i = 0; i < spotCount; i++) {
                    text += '.';
                }
                clickTip.text(text);
                if (spotCount === 2) {
                    spotCount = 0;
                } else {
                    spotCount++;
                }
            }, 500);
            $.ajax(href + '?id=' + subject_id, {
                type: 'get',
                dataType: 'json',
                success: function (result) {
                    if (result['success']) {
                        updateArchived(_this, result['archived'], subject_id);
                    } else {
                        alert(result['msg']);
                        _this.attr('hidden', false);
                        clickTip.attr('hidden', true);
                    }
                },
                error: function () {
                    clickTip.text('无法连接到服务器！');
                },
                complete: function () {
                    clearInterval(timer);
                }
            });
        }
    });
}

// bind related events
function updateArchived(_this, archived, subject_id) {
    let clickTip = _this.prev('.clickTip');
    clickTip.attr('hidden', true);
    _this.attr('hidden', false);

    switch (archived) {
        case 'added':
            _this.text('已添加');
            _this.attr('title', '点击搜索');
            bindClick(_this, '正在搜索', '/video/collect', subject_id);
            break;
        case 'playable':
            _this.text('可播放');
            _this.attr('title', '点击播放');
            bindClick(_this, '正在启动', '/video/play', subject_id);
            break;
        case 'idm':
            _this.text('IDM');
            _this.attr('title', '点击归档');
            bindClick(_this, '正在归档', '/video/temp', subject_id, '全部下载完成？');
            break;
        case 'downloading':
            _this.text('下载中');
            _this.attr('title', '点击归档');
            bindClick(_this, '正在归档', '/video/temp', subject_id, '全部下载完成？');
            break;
        case 'none':
            _this.text('找不到资源');
            _this.attr('title', '重新搜索');
            bindClick(_this, '正在搜索', '/video/collect', subject_id);
            break;
        default:
            alert('Unknown archived result');
    }
}

function updateMyMovies() {
    let user_id = prompt('Input user id', '132842700');
    if (user_id !== null) {
        $.ajax('/video/update?user_id=' + user_id, {
            type: 'get',
            dataType: 'json',
            success: function (result) {
                if (result['success']) {
                    alert(result['count'] + ' added');
                } else {
                    alert(result['msg']);
                }
            },
            error: function () {
                alert('无法连接到服务器！');
            },
        });
    }
}
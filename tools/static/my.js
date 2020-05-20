archiveMap = {
    added: {
        code: 0, text: '已添加', title: '点击搜索', func: function (_this, subject_id) {
            getJSON(_this, 'http://localhost:5000/video/collect?id=' + subject_id, '正在搜索', function (result) {
                updateArchived(_this, result['archived'], subject_id);
            });
        }
    },
    playable: {
        code: 1, text: '可播放', title: '点击播放', func: function (_this, subject_id) {
            getJSON(_this, 'http://localhost:5000/video/play?id=' + subject_id, '正在启动', function (result) {
                if (!result.success) {
                    alert('无法播放');
                }
                updateArchived(_this, 'playable', subject_id);
            });
        }
    },
    idm: {
        code: 2, text: 'IDM', title: '点击归档', func: function (_this, subject_id) {
            let yOrN = confirm('全部下载完成？');
            if (yOrN) {
                getJSON(_this, 'http://localhost:5000/video/archive?id=' + subject_id, '正在归档', function (result) {
                    updateArchived(_this, result['archived'], subject_id);
                })
            }
        }
    },
    downloading: {
        code: 3, text: '下载中', title: '点击归档', func: function (_this, subject_id) {
            let yOrN = confirm('全部下载完成？');
            if (yOrN) {
                getJSON(_this, 'http://localhost:5000/video/temp?id=' + subject_id, '正在归档', function (result) {
                    let a = result['archived'];
                    if (a === -2) {
                        alert('I/O错误');
                        updateArchived(_this, 'downloading', subject_id);
                    } else {
                        updateArchived(_this, a, subject_id);
                    }
                })
            }
        }
    },
};


(function () {
    $('.filter').on('change', function () {
        $('#form').submit();
    });

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

    $('.playBtn').each(function () {
        updateArchived($(this), $(this).data('archived'), $(this).data('id'));
    });

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

    $('#archiveBtn').on('click', function () {
        $('.batchSelect:checked').each(function () {
            // $(this).next('.archived').children('.playBtn').click();
        });
    });
})();

function updateArchived(_this, archived, subject_id) {
    if (archiveMap.hasOwnProperty(archived)) {
        let value = archiveMap[archived];
        _this.text(value['text']);
        _this.attr('title', value['title']);
        _this.off('click').on('click', null, null, function () {
            value['func'](_this, subject_id);
        });
    } else {
        _this.parent().prepend('<span>找不到资源！</span>');
        _this.remove();
    }
}

function getJSON(_this, url, tip, callback) {
    _this.attr('hidden', true);
    let clickTip = _this.prev();
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
    $.ajax(url, {
        type: 'get',
        dataType: 'json',
        success: function (result) {
            callback(result);
            clickTip.attr('hidden', true);
        },
        error: function () {
            clickTip.text('无法连接到服务器！');
        },
        complete: function () {
            _this.attr('hidden', false);
            clearInterval(timer);
        }
    });
}
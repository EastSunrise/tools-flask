archiveMap = {
    added: {
        code: 0, text: '已添加', title: '点击搜索', tip: '正在搜索', url: 'http://localhost:5000/video/collect?id='
    },
    playable: {
        code: 1, text: '可播放', title: '点击播放', tip: '正在启动', url: 'http://localhost:5000/video/play?id='
    },
    idm: {
        code: 2,
        text: 'IDM',
        title: '点击归档',
        tip: '正在归档',
        confirm: '全部下载完成？',
        url: 'http://localhost:5000/video/archive?id='
    },
    downloading: {
        code: 3,
        text: '下载中',
        title: '点击归档',
        tip: '正在归档',
        confirm: '全部下载完成？',
        url: 'http://localhost:5000/video/temp?id=',
    },
    none: {
        code: -1,
        text: '找不到资源',
        title: '重新搜索',
        tip: '正在搜索',
        url: '/video/collect?id='
    }
};

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

    $('#archiveBtn').on('click', function () {
        $('.batchSelect:checked').each(function () {
            // $(this).next('.archived').children('.playBtn').click();
        });
    });
})();

// bind related events
function updateArchived(_this, archived, subject_id) {
    let clickTip = _this.prev('.clickTip');
    if (archiveMap.hasOwnProperty(archived)) {
        let value = archiveMap[archived];
        _this.attr('hidden', false);
        clickTip.attr('hidden', true);
        _this.text(value['text']);
        _this.attr('title', value['title']);
        _this.off('click').on('click', function () {
            if (!value['confirm'] || confirm(value['confirm'])) {
                _this.attr('hidden', true);
                clickTip.text(value['tip']);
                clickTip.attr('hidden', false);
                let spotCount = 0;
                let timer = setInterval(function () {
                    let text = value['tip'] + '.';
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
                $.ajax(value['url'] + subject_id, {
                    type: 'get',
                    dataType: 'json',
                    success: function (result) {
                        if (result['success']) {
                            updateArchived(_this, result['archived'], subject_id);
                        } else {
                            alert(result['msg']);
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
    } else {
        alert('Unknown archived result');
    }
}
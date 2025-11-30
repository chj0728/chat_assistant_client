/*
@file
@brief a simple demo to recognize speech from microphone

@author		taozhang9
@date		2016/05/27
*/

#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <string.h>
#include "speech_recognizer.h"
#include "linuxrec.h"

using namespace AIKIT;

#define SR_DBGON 1
#if SR_DBGON == 1
#	define sr_dbg printf
#else
#	define sr_dbg
#endif

#define DEFAULT_FORMAT		\
{\
	WAVE_FORMAT_PCM,	\
	1,			\
	16000,			\
	32000,			\
	2,			\
	16,			\
	sizeof(WAVEFORMATEX)	\
}

/* internal state */
enum {
	SR_STATE_INIT,
	SR_STATE_STARTED
};


#define SR_MALLOC malloc
#define SR_MFREE  free
#define SR_MEMSET	memset


static void Sleep(size_t ms)
{
	usleep(ms*1000);
}

int write_count = 0;

static void end_sr_on_error(struct speech_rec *sr, int errcode)
{
	if(sr->aud_src == SR_MIC)
		stop_record(sr->recorder);
	
	if (sr->handle) {
		AIKIT_End(sr->handle);
		sr->handle = NULL;
	}
	sr->state = SR_STATE_INIT;
}

/* the record call back */
static void ivw_cb(char *data, unsigned long len, void *user_para)
{
	int errcode;
	struct speech_rec *sr;

	if(len == 0 || data == NULL)
		return;

	sr = (struct speech_rec *)user_para;

	if(sr == NULL)
		return;
	if (sr->state < SR_STATE_STARTED)
		return; /* ignore the data if error/vad happened */
	
	errcode = sr_write_audio_data(sr, data, len);
	if (errcode) {
		end_sr_on_error(sr, errcode);
		return;
	}
}

/* devid will be ignored if aud_src is not SR_MIC ; use get_default_dev_id
 * to use the default input device. Currently the device list function is
 * not provided yet. 
 */

int sr_init_ex(struct speech_rec * sr, int count, 
			enum sr_audsrc aud_src, record_dev_id devid)
{
	int ret = 0;
	WAVEFORMATEX wavfmt = DEFAULT_FORMAT;
	AIKIT_ParamBuilder* paramBuilder = nullptr;

	if (aud_src == SR_MIC && get_input_dev_num() == 0) {
		return -E_SR_NOACTIVEDEVICE;
	}

	if (!sr)
		return -E_SR_INVAL;

	SR_MEMSET(sr, 0, sizeof(struct speech_rec));
	sr->state = SR_STATE_INIT;
	sr->aud_src = aud_src;
	sr->handle=NULL;
	sr->ABILITY="e867a88f2";
	sr->dataBuilder=nullptr;
	sr->dataBuilder=AIKIT_DataBuilder::create();

	int* index=nullptr;
	index = (int *)malloc(count * sizeof(int));
    for (int i = 0; i < count;++i)
        index[i] = i;
    ret = AIKIT_SpecifyDataSet(sr->ABILITY, "key_word", index, count);
    printf("AIKIT_SpecifyDataSet:%d\n", ret);
    if(ret != 0){
		free(index);
		return ret;
	}
	free(index);
	
	paramBuilder=AIKIT_ParamBuilder::create();
	paramBuilder->param("wdec_param_nCmThreshold", "0 0:1000", strlen("0 0:1000"));
	paramBuilder->param("gramLoad",true);
	ret = AIKIT_Start(sr->ABILITY, AIKIT_Builder::build(paramBuilder), nullptr, &sr->handle);
	printf("AIKIT_Start:%d\n", ret);
	if (0 != ret)
	{
		// sr_dbg("AIKIT_Start failed! error code:%d\n", ret);
		return ret;
	}

	if (aud_src == SR_MIC) {
		ret = create_recorder(&sr->recorder, ivw_cb, (void*)sr);
		if (sr->recorder == NULL || ret != 0) {
			// sr_dbg("create recorder failed: %d\n", ret);
			ret = -E_SR_RECORDFAIL;
			goto fail;
		}

		wavfmt.nSamplesPerSec = 16000;
		wavfmt.nAvgBytesPerSec = wavfmt.nBlockAlign * wavfmt.nSamplesPerSec;
	
		ret = open_recorder(sr->recorder, devid, &wavfmt);
		if (ret != 0) {
			// sr_dbg("recorder open failed: %d\n", ret);
			ret = -E_SR_RECORDFAIL;
			goto fail;
		}
	}

	if(paramBuilder != nullptr)
	{
		delete paramBuilder;
		paramBuilder = nullptr;
	}

	return 0;

fail:
	if (sr->recorder) {
		destroy_recorder(sr->recorder);
		sr->recorder = NULL;
	}

	SR_MEMSET(&sr->notif, 0, sizeof(sr->notif));

	return ret;
}

/* use the default input device to capture the audio. see sr_init_ex */
int sr_init(struct speech_rec * sr, int count, 
		enum sr_audsrc aud_src)
{
	return sr_init_ex(sr, count, aud_src, 
			get_default_input_dev());
}

int sr_start_listening(struct speech_rec *sr)
{
	int ret = 0;

	if (sr->state >= SR_STATE_STARTED) {
		// sr_dbg("already STARTED.\n");
		return -E_SR_ALREADY;
	}

	if (sr->aud_src == SR_MIC) {
		ret = start_record(sr->recorder);
		if (ret != 0) {
			// sr_dbg("start record failed: %d\n", ret);
			if(sr->handle)
				AIKIT_End(sr->handle);
			sr->handle = NULL;
			return -E_SR_RECORDFAIL;
		}
	}

	sr->state = SR_STATE_STARTED;

	printf("Start Listening...\n");

	return 0;
}

/* after stop_record, there are still some data callbacks */
static void wait_for_rec_stop(struct recorder *rec, unsigned int timeout_ms)
{
	while (!is_record_stopped(rec)) {
		Sleep(1);
		if (timeout_ms != (unsigned int)-1)
			if (0 == timeout_ms--)
				break;
	}
}

int sr_stop_listening(struct speech_rec *sr)
{
	int ret = 0;

	if (sr->state < SR_STATE_STARTED) {
		// sr_dbg("Not started or already stopped.\n");
		return 0;
	}

	if (sr->aud_src == SR_MIC) {
		ret = stop_record(sr->recorder);
		if (ret != 0) {
			sr_dbg("Stop failed! \n");
			return -E_SR_RECORDFAIL;
		}
		wait_for_rec_stop(sr->recorder, (unsigned int)-1);
	}
	sr->state = SR_STATE_INIT;

	ret = AIKIT_End(sr->handle);
	sr->handle = NULL;
	return 0;
}

int sr_write_audio_data(struct speech_rec *sr, char *data, unsigned int len)
{
	// sr_dbg("sr_write_audio_data: %d\n",write_count++);

	AiAudio* aiAudio_raw = NULL;
	int ret = 0;

	if (!sr )
		return -E_SR_INVAL;
	if (!data || !len)
		return 0;

	sr->dataBuilder->clear();
	aiAudio_raw = AiAudio::get("wav")->data(data, len)->valid();
	sr->dataBuilder->payload(aiAudio_raw);
	ret = AIKIT_Write(sr->handle, AIKIT_Builder::build(sr->dataBuilder));
	if (ret != 0)
	{
		end_sr_on_error(sr, ret);
		return ret;
	}

	return 0;
}

void sr_uninit(struct speech_rec * sr)
{
	if (sr->recorder) {
		if(!is_record_stopped(sr->recorder))
			stop_record(sr->recorder);
		close_recorder(sr->recorder);
		destroy_recorder(sr->recorder);
		sr->recorder = NULL;
	}

	if(sr->dataBuilder != nullptr)
	{
		delete sr->dataBuilder;
		sr->dataBuilder = nullptr;
	}
}

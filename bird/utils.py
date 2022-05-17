import os
import json
import pickle
import time
import random
import numpy as np
from math import ceil
import pdb
import torch
random.seed(1234)
np.random.seed(1234)


def get_ref_sents(test_file):
    all_references = []
    with open(test_file, 'r', encoding = 'utf-8') as file:
        for idx, line in enumerate(file):
            jterm = json.loads(line)
            all_references.extend([' '.join(c) for c in jterm['description']])
    return all_references


def L2_SP(args, model, pretrain_model_dict):
    loss_existing_layers = []
    for name, param in model.named_parameters():
        if 'weight' in name:
            #print('\nPara ', param.size())
            #print('Pretrain ', pretrain_model_dict[name.replace('module.','')].size())
            loss_existing_layers.append(torch.pow(param-pretrain_model_dict[name], 2).sum()/2)
    loss = args.l2_wd * sum(loss_existing_layers)
    #print('L2 SP ', loss)
    return loss

def save_para(args, path):
    with open(path, "w", encoding="utf-8") as f:
        args = json.dumps(vars(args), indent=4)
        f.write(args)

def load_images(data_path):
    print("load grid feats ...")
    image_path = os.path.join(data_path, 'full_img.pkl')
    datas = pickle.load(open(image_path, 'rb'))
    images = {}
    for key in datas:
        images[key.replace('.jpg', '').split('/')[-1]] = datas[key]
    print('Total images ', len(images))
    return images

def get_images_name(data_path):
    images = []
    file_path = os.path.join(data_path, 'grid_feats')
    images_name = os.listdir(file_path) # e.g. test1-0-0-img0.npy
    images.extend(images_name) 
    return images


def load_vocabs(data_path):
    dict_path = os.path.join(data_path)
    word2id = json.load(open(dict_path, 'r', encoding='utf-8'))
    id2word = {word2id[key]:key for key in word2id}
    print('Vocabulary Size', len(word2id))
    return word2id, id2word

def load_data(data_path, dataset, images):
    all_datas = {}
    for split in ['train', 'val', 'test']:
        datas = []
        dropdata = 0
        if not os.path.exists(data_path + split + '.json'):
            continue
        with open(data_path + split + '.json', 'r', encoding='utf-8') as fin:
            for line in fin:
                jterm = json.loads(line.strip())
                if dataset == 'bird':
                    if jterm['img1'] in images and jterm['img2'] in images:
                        if split == 'train':
                            datas.append(jterm)
                        else:
                            # change multi description to one description per data
                            for des in jterm['description']:
                                new_jterm = {}
                                new_jterm['img1'] = jterm['img1']
                                new_jterm['img2'] = jterm['img2']
                                new_jterm['description'] = des
                                datas.append(new_jterm)
                    else:
                        dropdata += 1
                elif dataset == 'cub':
                    jterm['img'] = jterm['img'].split('/')[-1]
                    if jterm['img'] in images:
                        if split == 'train':
                            datas.append(jterm)
                        else:
                            # change multi description to one description per data
                            for des in jterm['description']:
                                new_jterm = {}
                                new_jterm['img'] = jterm['img']
                                new_jterm['description'] = des
                                datas.append(new_jterm)
                    else:
                        dropdata += 1
                elif dataset == 'nabirds':
                    datas.append(jterm)
        print('dataset:', dataset, 'Total True Label datas ', len(datas), 'drop ', dropdata, ' data')
        random.shuffle(datas)
        all_datas[split] = datas
    return all_datas

def load_neg_data(neg_name, data_path, dataset, images=None):
    all_datas = {}
    for split in ['train', 'val']:
        datas = []
        print("read: "+data_path + split + '_{}.json'.format(neg_name))
        with open(data_path + split + '_{}.json'.format(neg_name), 'r', encoding='utf-8') as fin:
            for line in fin:
                jterm = json.loads(line.strip())
                # change multi description to one description per data
                for des in jterm['sentences']:
                    new_jterm = {}
                    new_jterm['img1'] = jterm['img1'].replace('.jpg', '')
                    new_jterm['img2'] = jterm['img2'].replace('.jpg', '')
                    if new_jterm['img1'] in images and new_jterm['img2'] in images:
                        new_jterm['description'] = des.split(' ')
                        new_jterm['negs'] = [cap.split(' ') for cap in jterm['neg_samples']]
                        datas.append(new_jterm)
        print('dataset:', dataset, 'Negtive {} datas '.format(split), len(datas))
        random.shuffle(datas)
        all_datas[split] = datas
    return all_datas

def load_neg_data_cub(neg_num, data_path, dataset, images=None):
    all_datas = {}
    for split in ['train', 'val']:
        datas = []
        print("read: "+data_path + split + '_neg_tfidf{}.json'.format(neg_num))
        with open(data_path + split + '_neg_tfidf{}.json'.format(neg_num), 'r', encoding='utf-8') as fin:
            for line in fin:
                jterm = json.loads(line.strip())
                # change multi description to one description per data
                for des in jterm['sentences']:
                    new_jterm = {}
                    new_jterm['img'] = jterm['img']
                    new_jterm['description'] = des.split(' ')
                    new_jterm['negs'] = [cap.split(' ') for cap in jterm['neg_samples']]
                    datas.append(new_jterm)
        print('dataset:', dataset, 'Negtive {} datas '.format(split), len(datas))
        random.shuffle(datas)
        all_datas[split] = datas
    return all_datas

def noam_schedule(step, warmup_step=4000):
    """ original Transformer schedule"""
    if step <= warmup_step:
        return step / warmup_step
    return (warmup_step ** 0.5) * (step ** -0.5)


def warmup_linear(step, warmup_step, tot_step):
    """ BERT schedule """
    if step < warmup_step:
        return step / warmup_step
    return max(0, (tot_step-step)/(tot_step-warmup_step))

def finetune_lr_schedule(global_step, lr):
    if global_step < 10000:
        this_step_lr = lr
    elif global_step < 20000:
        this_step_lr = lr / 2
    else:
        this_step_lr = lr / 4
    return this_step_lr 


def get_lr_sched(global_step, args, pretrain=True):
    # learning rate scheduling
    if pretrain:
        lr_this_step = args.lr * noam_schedule(
            global_step, args.warmup_steps)
        if lr_this_step <= 0:
            lr_this_step = 1e-8
    else:
        lr_this_step = finetune_lr_schedule(global_step, args.lr)
    return lr_this_step

class Logger():
    def __init__(self, output_path, is_train=True):
        self.is_train = is_train
        self.out_path = output_path
        if is_train:
            self.log_name = os.path.join(output_path, 'train_log.txt')
            with open(self.log_name, 'a') as log_file:
                now = time.strftime("%c")
                log_file.write('========== Training Log (%s) ==========\n' % now)
        else:
            self.log_name = os.path.join(output_path, 'eval_log.txt')
            with open(self.log_name, 'a') as log_file:
                now = time.strftime("%c")
                log_file.write('========== Evaluation Log (%s) ==========\n' % now)


    def print_train_stats(self, task, epoch, global_step, report_loss, time):
        message = 'task: %s, epoch: %d, global_step: %d, report_loss: %.5f, time: %.2f' % (task, epoch, global_step, report_loss, time)
        with open(self.log_name, 'a') as log_file:
            log_file.write('%s\n' % message)

    def print_eval_stats(self, step, stats, no_beat=-1):
        if no_beat >= 0:
            message = '[Step: %d  no_beat: %d] ' % (step, no_beat)
        else:
            message = '[Step: %d] ' % (step)
        for k, v in stats.items():
            message += '%s: %.4f ' % (k, v)
        with open(self.log_name, 'a') as log_file:
            log_file.write('%s\n' % message)





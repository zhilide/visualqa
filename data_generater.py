import os
import pickle
import shutil
import matplotlib.pyplot as plt
import numpy as np
import skimage.io as io

import keras.backend as K
from keras import Model
from keras.applications import VGG19
from keras.preprocessing.image import load_img, img_to_array
from visualqa.config import Config
from visualqa.parse import DataParser


class DataGenerate(object):
	def __init__(self, config):
		self.config = config
		base_model = VGG19(weights='imagenet', include_top=False)
		self.model = Model(inputs=base_model.input, outputs=base_model.get_layer('block5_conv4').output)
		self._data = DataParser(config)
		if not os.path.isfile(self.config.save_data_file):
			self._data.parse()
			self._data.save_result()
			self._data.save_data()
		else:
			with open(self.config.save_data_file, 'br') as f:
				self._data = pickle.load(f)
		self.cur_index = 0

	def image_process(self, image_file, image_rows=224, image_clos=224):
		"""
		modefy the iamge format to fit vgg19 input
		:param image_clos:
		:param image_rows:
		:param image_file: PIL image instance
		:return: array to fit vgg19 input
		"""

		image = load_img(image_file, target_size=(image_rows, image_clos))
		if K.image_data_format() == 'channels_last':
			input = img_to_array(image, data_format='channels_last')
			input = input.reshape(image_rows, image_clos, 3)
		else:
			input = img_to_array(image, data_format='channels_first')
			input = input.reshape(3, image_rows, image_clos)
		return input

	def local_region_feature_extraction(self, img_input):
		"""
		:param img_input: input image with size (224,224,3)
		:return:image feature with sharpe (14, 14, 512)
		"""
		img_input = np.expand_dims(img_input, axis=0)
		return self.model.predict(img_input)

	def snack_reshape(self, visual_feature):
		"""
		convert visual feature to vector series
		:param visual_feature: tensor or array with size (14, 14, 512)
		:return: vector series
		"""
		feature_rows = visual_feature.shape[0]
		feature_clos = visual_feature.shape[1]
		size = visual_feature.shape[2]
		# print('feature shape:({},{})'.format(feature_rows, feature_clos))
		for i in range(feature_rows):
			if i & 2 == 0:
				visual_feature[i] = visual_feature[i][-1::-1]
		return visual_feature.reshape(feature_rows * feature_clos, size)

	def oht_encode(self, answer):
		return answer-1

	def _encode_image(self):
		self.cur_index = 0
		for image_id in self._data.train_dataset['image_id']:
			image_file = self.config.train_img_dir + str(image_id).zfill(12) + '.jpg'
			feature_file = os.path.join(self.config.train_image_feature_dir, str(image_id) + '.npy')
			if not os.path.isfile(image_file):
				continue
			if os.path.isfile(feature_file):
				shutil.copy(feature_file, r'D:\visualqa\upload')
				continue
			image_array = self.image_process(image_file)
			[image_feature] = self.local_region_feature_extraction(image_array)
			image_feature = self.snack_reshape(image_feature)
			np.save(feature_file, image_feature)
			print('train image feature:%d saved' % image_id)

		for image_id in self._data.val_dataset['image_id']:
			image_file = self.config.val_img_dir + str(image_id).zfill(12) + '.jpg'
			feature_file = os.path.join(self.config.val_image_feature_dir, str(image_id) + '.npy')
			if not os.path.isfile(image_file):
				continue
			if os.path.isfile(feature_file):
				continue
			image_array = self.image_process(image_file)
			[image_feature] = self.local_region_feature_extraction(image_array)
			image_feature = self.snack_reshape(image_feature)
			np.save(feature_file, image_feature)
			print('val image feature:%d saved' % image_id)

	def get_image_feature(self, image_ids):
		img_feature = []
		if self.config.data_type == 'train':
			for img_id in image_ids:
				img_f = np.load(os.path.join(self.config.train_image_feature_dir, str(img_id) + '.npy'))
				img_feature.append(img_f)
		else:
			for img_id in image_ids:
				img_f = np.load(os.path.join(self.config.val_image_feature_dir, str(img_id) + '.npy'))
				img_feature.append(img_f)
		return np.array(img_feature)

	def get_config(self):
		steps_per_epoch = self._data.train_sample_size // self.config.batch_size
		vocab_size = self._data.word_size
		max_question_size = self._data.max_question_size
		answer_size = self._data.answer_word_size
		config = {'steps_per_epoch': steps_per_epoch, 'train_size': self._data.train_sample_size,
				  'vocab_size': vocab_size, 'max_question_size': max_question_size,
				  'answer_word_size': answer_size
				  }
		return config

	def generate_data(self):
		"""
		:param question_type:
		:param iter_num:
		:param batch_size:
		:return: (img, question, answer)
		"""
		if self.config.data_type == 'train':
			data = self._data.train_dataset
			sample_size = self._data.train_sample_size
		else:
			data = self._data.val_dataset
			sample_size = self._data.val_dataset

		image_ids = data['image_id']
		questions = np.array(list(data['question']))
		answers = data['answer']

		while True:
			if self.cur_index + self.config.batch_size > sample_size:
				mask = np.arange(sample_size)
				np.random.shuffle(mask)
				image_ids = image_ids[mask]
				questions = questions[mask]
				answers = answers[mask]
				self.cur_index = 0

			image = image_ids.iloc[self.cur_index: self.cur_index + self.config.batch_size]
			image_input = self.get_image_feature(image)

			questions_input = questions[self.cur_index: self.cur_index + self.config.batch_size]

			answers_input = answers.iloc[self.cur_index: self.cur_index + self.config.batch_size]
			answers_input = np.array(list(answers_input.apply(self.oht_encode)))

			self.cur_index += self.config.batch_size
			yield ([image_input, questions_input], answers_input)

	def show_data_random(self):
		rand_index = np.random.randint(0, len(self._data.train_dataset))
		d = self._data.train_dataset.iloc[rand_index]
		image_file = self.config.train_img_dir + str(d['image_id']).zfill(12) + '.jpg'
		question = d['question']
		answer = d['answer']
		q = ' '.join(self._data.index2words[x] for x in question if x != 0)
		a = self._data.index2words[answer]
		print('question:\n' + q)
		print('answer:\n' + a)
		im = io.imread(image_file)
		plt.axis('off')
		plt.imshow(im)
		plt.show()


if __name__ == '__main__':
	config = Config()
	data = DataGenerate(config)
	# data._encode_image()
	train = data.generate_data()
	[a, b], c = next(train)
	data.show_data_random()
